<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as THREE from 'three'
  import { OrbitControls } from 'three-stdlib'
  // Stats removed per requirements

  let container: HTMLDivElement
  let canvas: HTMLCanvasElement | null = null
  let overlayCanvas: HTMLCanvasElement | null = null
  let overlayCtx: CanvasRenderingContext2D | null = null

  let renderer: THREE.WebGLRenderer
  let scene: THREE.Scene
  let camera: THREE.PerspectiveCamera
  let controls: OrbitControls
  // let stats: Stats

  let points: THREE.Points | null = null
  let positionsArray: Float32Array | null = null
  let colorsArray: Float32Array | null = null
  let originalColorsArray: Float32Array | null = null
  // One-level undo snapshots for last deletion
  let lastPositionsSnapshot: Float32Array | null = null
  let lastColorsSnapshot: Float32Array | null = null
  let lastOriginalColorsSnapshot: Float32Array | null = null
  let lastSelectionMask: Uint8Array | null = null

  let selectionWorker: Worker | null = null
  let selectionRect: { x0: number; y0: number; x1: number; y1: number } | null = null
  let selectionPolygon: Array<{ x: number; y: number }> | null = null
  let isSelecting = false
  let isLasso = false
  let selectionResult: Uint8Array | null = null
  let wasControlsEnabled = true
  let resizeObserver: ResizeObserver | null = null

  let dpr = Math.min(window.devicePixelRatio || 1, 2)

  // Expose undo availability to parent via bind:canUndo
  export let canUndo = false
  export let defaultColor: [number, number, number] = [1,1,1]
  export let backgroundColor: [number, number, number] = [0.043,0.043,0.043]
  export let selectionColor: [number, number, number] = [1,0.8,0.2]
  export let pointCount = 0
  export let isDirty = false
  export let addMode = false
  export let currentView: 'original' | 'cleaned' | 'delta' | null = null

  export function clear() {
    if (points) {
      scene.remove(points)
      ;(points.geometry as THREE.BufferGeometry).dispose()
      ;(points.material as THREE.Material).dispose()
      points = null
    }
    positionsArray = null
    colorsArray = null
    selectionResult = null
    originalColorsArray = null
    // Reset undo state
    lastPositionsSnapshot = null
    lastColorsSnapshot = null
    lastOriginalColorsSnapshot = null
    lastSelectionMask = null
    canUndo = false
    isDirty = false
  }

  export function resetView() {
    if (!points) return
    fitCameraToObject(points)
  }

  export async function loadPCDFromURL(url: string) {
    const { PCDLoader } = await import('three-stdlib')
    const loader = new PCDLoader()
    return new Promise<void>((resolve, reject) => {
      loader.load(
        url,
        (obj: THREE.Points) => {
          setupPoints(obj)
          resolve()
        },
        undefined,
        (err: ErrorEvent) => reject(err)
      )
    })
  }

  export async function loadPCDFile(file: File) {
    const blobURL = URL.createObjectURL(file)
    try {
      await loadPCDFromURL(blobURL)
    } finally {
      URL.revokeObjectURL(blobURL)
    }
  }

  // Return a copy of the current selection mask (1 for selected, 0 otherwise)
  export function getSelectionMask(): Uint8Array | null {
    return selectionResult ? new Uint8Array(selectionResult) : null
  }

  // Return a subset of points corresponding to current selection
  export function getSelectedSubset(): { positions: Float32Array; colors?: Float32Array } | null {
    if (!positionsArray || !selectionResult) return null
    const count = positionsArray.length / 3
    let selectedCount = 0
    for (let i = 0; i < count; i++) if (selectionResult[i] === 1) selectedCount++
    if (selectedCount === 0) return { positions: new Float32Array(0), colors: colorsArray ? new Float32Array(0) : undefined }
    const outPos = new Float32Array(selectedCount * 3)
    const outCol = colorsArray ? new Float32Array(selectedCount * 3) : undefined
    let w = 0
    for (let i = 0; i < count; i++) {
      if (selectionResult[i] === 1) {
        const r = i * 3
        outPos[w] = positionsArray[r]
        outPos[w + 1] = positionsArray[r + 1]
        outPos[w + 2] = positionsArray[r + 2]
        if (outCol && colorsArray) {
          outCol[w] = colorsArray[r]
          outCol[w + 1] = colorsArray[r + 1]
          outCol[w + 2] = colorsArray[r + 2]
        }
        w += 3
      }
    }
    return { positions: outPos, colors: outCol }
  }

  // Return entire current point cloud buffers (copies)
  export function getPointCloudData(): { positions: Float32Array; colors?: Float32Array } | null {
    if (!positionsArray) return null
    return { positions: new Float32Array(positionsArray), colors: colorsArray ? new Float32Array(colorsArray) : undefined }
  }

  // Append points to the current geometry
  export function addPoints(positionsToAdd: Float32Array, colorsToAdd?: Float32Array) {
    if (!points || !positionsArray) return
    const hasColors = !!colorsArray || !!colorsToAdd
    const newLen = positionsArray.length + positionsToAdd.length
    const mergedPos = new Float32Array(newLen)
    mergedPos.set(positionsArray, 0)
    mergedPos.set(positionsToAdd, positionsArray.length)

    let mergedCol: Float32Array | null = null
    if (hasColors) {
      const existing = colorsArray ?? new Float32Array((positionsArray.length / 3) * 3)
      // If we had to create default colors for existing, fill with defaultColor
      if (!colorsArray) {
        const [r,g,b] = defaultColor
        for (let i = 0; i < existing.length; i += 3) { existing[i]=r; existing[i+1]=g; existing[i+2]=b }
      }
      const toAdd = colorsToAdd ?? (() => {
        const arr = new Float32Array((positionsToAdd.length / 3) * 3)
        const [r,g,b] = defaultColor
        for (let i = 0; i < arr.length; i += 3) { arr[i]=r; arr[i+1]=g; arr[i+2]=b }
        return arr
      })()
      mergedCol = new Float32Array(existing.length + toAdd.length)
      mergedCol.set(existing, 0)
      mergedCol.set(toAdd, existing.length)
    }

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(mergedPos, 3))
    if (mergedCol) {
      geom.setAttribute('color', new THREE.BufferAttribute(mergedCol, 3))
    }
    geom.computeBoundingSphere()
    geom.computeBoundingBox()

    const material = points.material as THREE.PointsMaterial
    scene.remove(points)
    ;(points.geometry as THREE.BufferGeometry).dispose()
    points = new THREE.Points(geom, material)
    points.frustumCulled = false
    ;(points.material as THREE.PointsMaterial).vertexColors = true
    ;(points.material as THREE.PointsMaterial).needsUpdate = true
    scene.add(points)

    positionsArray = mergedPos
    colorsArray = mergedCol
    originalColorsArray = mergedCol ? new Float32Array(mergedCol) : null
    selectionResult = null
    selectionRect = null
    canUndo = false
    pointCount = positionsArray.length / 3
  }

  export function deleteSelection() {
    if (!points || !positionsArray || !selectionResult) return

    // Take snapshot for undo
    lastPositionsSnapshot = new Float32Array(positionsArray)
    lastColorsSnapshot = colorsArray ? new Float32Array(colorsArray) : null
    lastOriginalColorsSnapshot = originalColorsArray ? new Float32Array(originalColorsArray) : null
    lastSelectionMask = new Uint8Array(selectionResult)

    const originalCount = positionsArray.length / 3
    let remainingCount = 0
    for (let i = 0; i < originalCount; i++) {
      if (selectionResult[i] === 0) remainingCount++
    }

    const newPositions = new Float32Array(remainingCount * 3)
    const newColors = colorsArray ? new Float32Array(remainingCount * 3) : null

    let write = 0
    for (let i = 0; i < originalCount; i++) {
      if (selectionResult[i] === 0) {
        const rIdx = i * 3
        newPositions[write] = positionsArray[rIdx]
        newPositions[write + 1] = positionsArray[rIdx + 1]
        newPositions[write + 2] = positionsArray[rIdx + 2]
        if (newColors && colorsArray) {
          newColors[write] = colorsArray[rIdx]
          newColors[write + 1] = colorsArray[rIdx + 1]
          newColors[write + 2] = colorsArray[rIdx + 2]
        }
        write += 3
      }
    }

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(newPositions, 3))
    if (newColors) {
      geom.setAttribute('color', new THREE.BufferAttribute(newColors, 3))
    }
    geom.computeBoundingSphere()

    const material = points.material as THREE.PointsMaterial
    scene.remove(points)
    ;(points.geometry as THREE.BufferGeometry).dispose()
    points = new THREE.Points(geom, material)
    points.frustumCulled = false
    ;(points.material as THREE.PointsMaterial).vertexColors = true
    ;(points.material as THREE.PointsMaterial).needsUpdate = true
    scene.add(points)

    positionsArray = newPositions
    colorsArray = newColors
    originalColorsArray = newColors ? new Float32Array(newColors) : null
    selectionResult = null
    selectionRect = null
    canUndo = true
    isDirty = true
  }

  export function undoLastDeletion() {
    if (!points || !lastPositionsSnapshot) return

    const restoredPositions = lastPositionsSnapshot
    const restoredColors = lastColorsSnapshot

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(restoredPositions, 3))
    if (restoredColors) {
      geom.setAttribute('color', new THREE.BufferAttribute(restoredColors, 3))
    }
    geom.computeBoundingSphere()
    geom.computeBoundingBox()

    const material = points.material as THREE.PointsMaterial
    scene.remove(points)
    ;(points.geometry as THREE.BufferGeometry).dispose()
    points = new THREE.Points(geom, material)
    points.frustumCulled = false
    ;(points.material as THREE.PointsMaterial).vertexColors = true
    ;(points.material as THREE.PointsMaterial).needsUpdate = true
    scene.add(points)

    positionsArray = restoredPositions
    colorsArray = restoredColors
    originalColorsArray = lastOriginalColorsSnapshot ? new Float32Array(lastOriginalColorsSnapshot) : (restoredColors ? new Float32Array(restoredColors) : null)
    // Restore previous selection so user can delete again
    selectionResult = lastSelectionMask ? new Uint8Array(lastSelectionMask) : null
    if (selectionResult) {
      applySelectionHighlight(selectionResult)
    }
    selectionRect = null

    // Clear undo (single-level)
    lastPositionsSnapshot = null
    lastColorsSnapshot = null
    lastOriginalColorsSnapshot = null
    lastSelectionMask = null
    canUndo = false
    // restored to previous, assume no dirty changes left for this simple model
    isDirty = false
  }

  function setupPoints(obj: THREE.Points) {
    clear()
    // Normalize material for performance
    const material = new THREE.PointsMaterial({
      size: 1.2,
      sizeAttenuation: true,
      vertexColors: true,
    })
    if (obj.material && (obj.material as any).size) {
      material.size = (obj.material as any).size
    }

    const srcGeom = obj.geometry as THREE.BufferGeometry
    const pos = srcGeom.getAttribute('position') as THREE.BufferAttribute
    positionsArray = new Float32Array(pos.array as ArrayLike<number>)

    const colorAttr = srcGeom.getAttribute('color') as THREE.BufferAttribute | undefined
    colorsArray = colorAttr ? new Float32Array(colorAttr.array as ArrayLike<number>) : null

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(positionsArray, 3))
    if (!colorsArray) {
      // Create default colors if absent
      colorsArray = new Float32Array((positionsArray.length / 3) * 3)
      const [r,g,b] = defaultColor
      for (let i = 0; i < colorsArray.length; i += 3) {
        colorsArray[i] = r
        colorsArray[i + 1] = g
        colorsArray[i + 2] = b
      }
    }
    geom.setAttribute('color', new THREE.BufferAttribute(colorsArray, 3))
    originalColorsArray = new Float32Array(colorsArray)
    geom.computeBoundingSphere()
    geom.computeBoundingBox()

    points = new THREE.Points(geom, material)
    ;(points.material as THREE.PointsMaterial).vertexColors = true
    ;(points.material as THREE.PointsMaterial).needsUpdate = true
    scene.add(points)
    fitCameraToObject(points)
    // Reset undo availability on new data
    canUndo = false
    lastPositionsSnapshot = null
    lastColorsSnapshot = null
    lastOriginalColorsSnapshot = null
    pointCount = positionsArray.length / 3
    isDirty = false
  }

  function restoreOriginalColors() {
    if (!points) return
    const colorAttr = (points.geometry as THREE.BufferGeometry).getAttribute('color') as THREE.BufferAttribute | undefined
    if (!colorAttr || !originalColorsArray) return
    const arr = colorAttr.array as Float32Array
    if (arr.length !== originalColorsArray.length) return
    arr.set(originalColorsArray)
    colorAttr.needsUpdate = true
  }

  function applySelectionHighlight(mask: Uint8Array) {
    if (!points) return
    const geom = points.geometry as THREE.BufferGeometry
    const colorAttr = geom.getAttribute('color') as THREE.BufferAttribute | undefined
    if (!colorAttr) return
    const arr = colorAttr.array as Float32Array
    const count = arr.length / 3
    if (!originalColorsArray || originalColorsArray.length !== arr.length) {
      originalColorsArray = new Float32Array(arr)
    }
    const highlightR = selectionColor[0], highlightG = selectionColor[1], highlightB = selectionColor[2]
    for (let i = 0; i < count; i++) {
      const j = i * 3
      if (mask[i] === 1) {
        arr[j] = highlightR
        arr[j + 1] = highlightG
        arr[j + 2] = highlightB
      } else {
        arr[j] = originalColorsArray[j]
        arr[j + 1] = originalColorsArray[j + 1]
        arr[j + 2] = originalColorsArray[j + 2]
      }
    }
    colorAttr.needsUpdate = true
  }

  function fitCameraToObject(object: THREE.Object3D) {
    const box = new THREE.Box3().setFromObject(object)
    const size = new THREE.Vector3()
    box.getSize(size)
    const center = new THREE.Vector3()
    box.getCenter(center)

    // Ensure non-degenerate size
    const maxSize = Math.max(size.x, size.y, size.z, 1e-6)
    const fitHeightDistance = maxSize / (2 * Math.atan((Math.PI * camera.fov) / 360))
    const fitWidthDistance = fitHeightDistance / Math.max(camera.aspect, 1e-6)
    const distance = Math.max(fitHeightDistance, fitWidthDistance)

    const toTarget = new THREE.Vector3().copy(controls.target).sub(camera.position)
    if (toTarget.lengthSq() < 1e-12) {
      toTarget.set(0, 0, 1) // fallback forward
    }
    const direction = toTarget.normalize().multiplyScalar(-1)

    camera.near = Math.max(0.001, distance / 1000)
    camera.far = distance * 1000
    camera.updateProjectionMatrix()

    camera.position.copy(direction.multiplyScalar(distance).add(center))
    controls.maxDistance = distance * 10
    controls.target.copy(center)
    controls.update()
  }

  function init() {
    scene = new THREE.Scene()
    scene.background = new THREE.Color(backgroundColor[0], backgroundColor[1], backgroundColor[2])

    camera = new THREE.PerspectiveCamera(60, 1, 0.001, 1e8)
    camera.position.set(0, 0, 10)

    renderer = new THREE.WebGLRenderer({ canvas: canvas!, antialias: false, powerPreference: 'high-performance', alpha: false, depth: true, logarithmicDepthBuffer: true })
    renderer.setPixelRatio(dpr)
    renderer.setSize(container.clientWidth, container.clientHeight)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.screenSpacePanning = true
    controls.enablePan = true
    controls.enableZoom = true
    controls.enableRotate = true
    controls.zoomSpeed = 2.5
    controls.minDistance = 0.0001
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    }
    // Custom wheel handler to move forward/back regardless of distance
    // renderer.domElement.addEventListener('wheel', onWheel, { passive: false })

    const ambient = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambient)
    const dir = new THREE.DirectionalLight(0xffffff, 0.4)
    dir.position.set(1, 1, 1)
    scene.add(dir)

    // FPS counter removed

    selectionWorker = new Worker(new URL('../workers/selectionWorker.ts', import.meta.url), { type: 'module' })
    selectionWorker.onmessage = (e: MessageEvent) => {
      selectionResult = e.data as Uint8Array
      if (selectionResult) {
        applySelectionHighlight(selectionResult)
      }
      // Clear rectangle overlay after selection completes
      selectionRect = null
      selectionPolygon = null
    }

    window.addEventListener('resize', onWindowResize)
    // Use capture phase to preempt OrbitControls when selecting
    renderer.domElement.addEventListener('pointerdown', onPointerDown, { capture: true })
    renderer.domElement.addEventListener('pointermove', onPointerMove, { capture: true })
    window.addEventListener('pointerup', onPointerUp, { capture: true })
    renderer.domElement.addEventListener('click', onCanvasClick)

    if (overlayCanvas) {
      overlayCanvas.width = container.clientWidth
      overlayCanvas.height = container.clientHeight
      overlayCtx = overlayCanvas.getContext('2d')
    }

    // Trigger initial size/layout once container is mounted
    onWindowResize()

    // React to container size changes, not just window resizes
    try {
      resizeObserver = new ResizeObserver(() => onWindowResize())
      resizeObserver.observe(container)
    } catch {}

    animate()
  }

  function onWindowResize() {
    if (!container) return
    const width = container.clientWidth
    const height = container.clientHeight
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height)
    if (overlayCanvas) {
      overlayCanvas.width = width
      overlayCanvas.height = height
    }
  }

  function screenRect() {
    if (!selectionRect) return null
    const x0 = Math.min(selectionRect.x0, selectionRect.x1)
    const y0 = Math.min(selectionRect.y0, selectionRect.y1)
    const x1 = Math.max(selectionRect.x0, selectionRect.x1)
    const y1 = Math.max(selectionRect.y0, selectionRect.y1)
    return { x0, y0, x1, y1 }
  }

  function onPointerDown(ev: PointerEvent) {
    if (!(ev.shiftKey || ev.ctrlKey)) return
    // If there was a previous highlight, restore original colors
    if (selectionResult) {
      restoreOriginalColors()
      selectionResult = null
    }
    isSelecting = true
    isLasso = !!ev.shiftKey && !ev.ctrlKey
    const rect = renderer.domElement.getBoundingClientRect()
    const px = ev.clientX - rect.left
    const py = ev.clientY - rect.top
    if (isLasso) {
      selectionPolygon = [{ x: px, y: py }]
      selectionRect = null
    } else {
      selectionRect = { x0: px, y0: py, x1: px, y1: py }
      selectionPolygon = null
    }
    // Disable controls while selecting and stop event from reaching OrbitControls
    wasControlsEnabled = controls.enabled
    controls.enabled = false
    try { (ev.target as Element).setPointerCapture?.(ev.pointerId) } catch {}
    ev.preventDefault()
    ev.stopImmediatePropagation?.()
  }

  function onPointerMove(ev: PointerEvent) {
    if (!isSelecting) return
    const rect = renderer.domElement.getBoundingClientRect()
    const px = ev.clientX - rect.left
    const py = ev.clientY - rect.top
    if (isLasso) {
      if (!selectionPolygon) selectionPolygon = []
      const last = selectionPolygon[selectionPolygon.length - 1]
      if (!last || ((px - last.x) * (px - last.x) + (py - last.y) * (py - last.y)) >= 4) {
        selectionPolygon.push({ x: px, y: py })
      }
    } else if (selectionRect) {
      selectionRect.x1 = px
      selectionRect.y1 = py
    }
    ev.preventDefault()
    ev.stopImmediatePropagation?.()
  }

  function onPointerUp() {
    if (!isSelecting) return
    isSelecting = false
    if ((!selectionRect && !selectionPolygon) || !points || !positionsArray) return
    // Re-enable controls after selection gesture ends
    controls.enabled = wasControlsEnabled

    const modelMatrix = points.matrixWorld.elements
    const viewMatrix = camera.matrixWorldInverse.elements
    const projMatrix = camera.projectionMatrix.elements
    // Use CSS pixel dimensions so selection rect (CSS) matches worker viewport
    const width = container.clientWidth
    const height = container.clientHeight

    selectionResult = null
    // Copy positions for worker and transfer the copy to avoid detaching live geometry buffer
    const positionsCopy = new Float32Array(positionsArray)
    if (isLasso && selectionPolygon && selectionPolygon.length >= 3) {
      // pack polygon as [x0,y0,x1,y1,...]
      const poly = new Float32Array(selectionPolygon.length * 2)
      for (let i = 0; i < selectionPolygon.length; i++) {
        poly[i * 2] = selectionPolygon[i].x
        poly[i * 2 + 1] = selectionPolygon[i].y
      }
      selectionWorker?.postMessage({
        positions: positionsCopy,
        modelMatrix: new Float32Array(modelMatrix),
        viewMatrix: new Float32Array(viewMatrix),
        projMatrix: new Float32Array(projMatrix),
        viewport: new Uint32Array([width, height]),
        mode: 'polygon',
        polygon: poly
      } as any, [ positionsCopy.buffer, poly.buffer ])
    } else if (selectionRect) {
      const { x0, y0, x1, y1 } = screenRect()!
      selectionWorker?.postMessage({
        positions: positionsCopy,
        modelMatrix: new Float32Array(modelMatrix),
        viewMatrix: new Float32Array(viewMatrix),
        projMatrix: new Float32Array(projMatrix),
        viewport: new Uint32Array([width, height]),
        mode: 'rect',
        rect: new Float32Array([x0, y0, x1, y1])
      } as any, [ positionsCopy.buffer ])
    }
  }

  function getClickNDC(ev: MouseEvent) {
    const width = renderer.domElement.clientWidth
    const height = renderer.domElement.clientHeight
    const x = (ev.offsetX / Math.max(1, width)) * 2 - 1
    const y = -(ev.offsetY / Math.max(1, height)) * 2 + 1
    return { x, y }
  }

  let raycaster: THREE.Raycaster = new THREE.Raycaster()

  function onCanvasClick(ev: MouseEvent) {
    if (!addMode) return
    if (currentView === 'delta') return
    if (isSelecting) return
    if (ev.button !== 0) return
    if (!positionsArray || !points) return
    // Prefer accurate raycast hit on Points with pixel-threshold; fallback to screen-nearest, then to plane
    const rect = renderer.domElement.getBoundingClientRect()
    const clickSX = ev.clientX - rect.left
    const clickSY = ev.clientY - rect.top
    const ndcX = (clickSX / rect.width) * 2 - 1
    const ndcY = -(clickSY / rect.height) * 2 + 1
    raycaster.setFromCamera({ x: ndcX, y: ndcY } as any, camera)
    // Convert a small pixel radius to world-units threshold at current distance
    const distance = camera.position.distanceTo(controls.target)
    const worldPerPixel = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * distance / Math.max(1, container.clientHeight)
    const pixelRadius = Math.max(6, 12 * dpr)
    raycaster.params.Points = { threshold: worldPerPixel * pixelRadius } as any

    let clickedX: number | null = null
    let clickedY: number | null = null

    const intersections = raycaster.intersectObject(points, false)
    if (intersections && intersections.length > 0) {
      const pLocal = points.worldToLocal(intersections[0].point.clone())
      clickedX = pLocal.x
      clickedY = pLocal.y
    }

    if (clickedX === null || clickedY === null) {
      try {
        const modelMatrix4 = points.matrixWorld
        const viewMatrix4 = camera.matrixWorldInverse
        const projMatrix4 = camera.projectionMatrix
        const mv = new THREE.Matrix4().multiplyMatrices(viewMatrix4, modelMatrix4)
        const mvp = new THREE.Matrix4().multiplyMatrices(projMatrix4, mv)
        const width = container.clientWidth
        const height = container.clientHeight
        const tmp = new THREE.Vector4()
        let bestIdx = -1
        let bestD2 = Infinity
        const maxR = Math.max(6, 12 * dpr)
        const maxR2 = maxR * maxR
        const countTotal = positionsArray.length / 3
        for (let i = 0; i < countTotal; i++) {
          const r = i * 3
          tmp.set(positionsArray[r], positionsArray[r + 1], positionsArray[r + 2], 1).applyMatrix4(mvp)
          const w = tmp.w
          if (w === 0) continue
          const sx = (tmp.x / w * 0.5 + 0.5) * width
          const sy = (1 - (tmp.y / w * 0.5 + 0.5)) * height
          const dx = sx - clickSX
          const dy = sy - clickSY
          const d2 = dx * dx + dy * dy
          if (d2 < bestD2 && d2 <= maxR2) { bestD2 = d2; bestIdx = r }
        }
        if (bestIdx >= 0) {
          clickedX = positionsArray[bestIdx]
          clickedY = positionsArray[bestIdx + 1]
        }
      } catch {}
    }

    if (clickedX === null || clickedY === null) {
      // Fallback: intersect click ray with the point cloud's local-XY plane (object Z normal) through cloud center
      // raycaster already set from camera above
      const q = new THREE.Quaternion()
      points.getWorldQuaternion(q)
      const normalWorld = new THREE.Vector3(0, 0, 1).applyQuaternion(q).normalize()

      const bbox = (points.geometry as THREE.BufferGeometry).boundingBox
      const centerLocal = new THREE.Vector3()
      if (bbox) bbox.getCenter(centerLocal)
      const centerWorld = points.localToWorld(centerLocal.clone())

      const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normalWorld, centerWorld)
      const hitWorld = new THREE.Vector3()
      const hasHit = raycaster.ray.intersectPlane(plane, hitWorld)
      if (!hasHit) return

      const hitLocal = points.worldToLocal(hitWorld.clone())
      clickedX = hitLocal.x
      clickedY = hitLocal.y
    }
    // Find up to 5 nearest neighbors in XY
    const count = positionsArray.length / 3
    const nearest: Array<{ d2: number; z: number }> = []
    for (let i = 0; i < count; i++) {
      const idx = i * 3
      const dx = positionsArray[idx] - clickedX
      const dy = positionsArray[idx + 1] - clickedY
      const d2 = dx * dx + dy * dy
      const z = positionsArray[idx + 2]
      if (nearest.length < 5) {
        nearest.push({ d2, z })
        if (nearest.length === 5) nearest.sort((a, b) => a.d2 - b.d2)
      } else if (d2 < nearest[nearest.length - 1].d2) {
        nearest[nearest.length - 1] = { d2, z }
        nearest.sort((a, b) => a.d2 - b.d2)
      }
    }

    if (nearest.length === 0) return
    // Median z of neighbors
    const zs = nearest.map(n => n.z).sort((a, b) => a - b)
    const mid = Math.floor(zs.length / 2)
    const medianZ = zs.length % 2 === 1 ? zs[mid] : (zs[mid - 1] + zs[mid]) / 2

    const toAdd = new Float32Array([clickedX, clickedY, medianZ])
    addPoints(toAdd)
    isDirty = true
  }

  function drawSelectionOverlay() {
    if (!overlayCtx || !overlayCanvas) return
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height)
    overlayCtx.save()
    overlayCtx.strokeStyle = `rgba(${Math.round(selectionColor[0]*255)}, ${Math.round(selectionColor[1]*255)}, ${Math.round(selectionColor[2]*255)}, 0.9)`
    overlayCtx.fillStyle = `rgba(${Math.round(selectionColor[0]*255)}, ${Math.round(selectionColor[1]*255)}, ${Math.round(selectionColor[2]*255)}, 0.15)`
    overlayCtx.lineWidth = 1
    overlayCtx.beginPath()
    if (selectionPolygon && selectionPolygon.length > 1) {
      overlayCtx.moveTo(selectionPolygon[0].x, selectionPolygon[0].y)
      for (let i = 1; i < selectionPolygon.length; i++) {
        overlayCtx.lineTo(selectionPolygon[i].x, selectionPolygon[i].y)
      }
      overlayCtx.closePath()
    } else if (selectionRect) {
      const r = screenRect()
      if (r) overlayCtx.rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
    }
    overlayCtx.fill()
    overlayCtx.stroke()
    overlayCtx.restore()
  }

  function onWheel(ev: WheelEvent) {
    // Disable default zoom to avoid OrbitControls dolly behavior
    ev.preventDefault()
    ev.stopPropagation()

    const delta = (ev.deltaY || 0)
    if (!isFinite(delta)) return

    // Compute movement amount in world units proportional to scene scale
    const baseStep = 0.002
    const dir = new THREE.Vector3()
    camera.getWorldDirection(dir) // unit vector pointing forward (-Z in camera space)

    // Distance scale based on bounding sphere or current distance to target
    const toTarget = new THREE.Vector3().copy(controls.target).sub(camera.position)
    const distance = Math.max(0.001, toTarget.length())
    const step = Math.sign(delta) * Math.max(baseStep * distance, 0.0005)

    // Move camera and target together (fly-style dolly), so we never stall near target
    camera.position.addScaledVector(dir, step)
    controls.target.addScaledVector(dir, step)
    controls.update()
  }

  function animate() {
    controls.update()
    renderer.render(scene, camera)
    drawSelectionOverlay()
    requestAnimationFrame(animate)
  }

  // Toggle rotation while in add mode to avoid conflicts; keep rotation in delta
  $: if (controls) {
    controls.enableRotate = !(addMode && currentView !== 'delta')
  }

  // react to color props changes
  $: if (scene) { scene.background = new THREE.Color(backgroundColor[0], backgroundColor[1], backgroundColor[2]) }
  $: if (points && positionsArray) {
    const geom = points.geometry as THREE.BufferGeometry
    const colorAttr = geom.getAttribute('color') as THREE.BufferAttribute | undefined
    if (colorAttr && (!originalColorsArray || originalColorsArray.length !== colorAttr.array.length)) {
      originalColorsArray = new Float32Array(colorAttr.array as Float32Array)
    }
    if (!colorsArray && colorAttr) {
      // regenerate default colors for point clouds without original per-vertex colors
      const arr = colorAttr.array as Float32Array
      const [r,g,b] = defaultColor
      for (let i = 0; i < arr.length; i += 3) { arr[i]=r; arr[i+1]=g; arr[i+2]=b }
      colorAttr.needsUpdate = true
    }
  }

  onMount(() => {
    init()
  })

  onDestroy(() => {
    window.removeEventListener('resize', onWindowResize)
    renderer?.domElement?.removeEventListener('pointerdown', onPointerDown)
    renderer?.domElement?.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    renderer?.domElement?.removeEventListener('click', onCanvasClick)
    renderer?.domElement?.removeEventListener('wheel', onWheel)
    selectionWorker?.terminate()
    try { resizeObserver?.disconnect() } catch {}
    clear()
    renderer?.dispose()
  })
</script>

<style>
  canvas { display: block; width: 100%; height: 100%; }
</style>

<div class="relative w-full h-full overflow-hidden rounded-lg bg-neutral-950" bind:this={container}>
  <canvas bind:this={canvas}></canvas>
  <canvas class="pointer-events-none absolute inset-0" bind:this={overlayCanvas}></canvas>
</div>



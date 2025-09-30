// Selection worker: rectangle and polygon
// Receives:
// - positions: Float32Array of XYZ triples
// - modelMatrix, viewMatrix, projMatrix: Float32Array(16) each
// - viewport: Uint32Array([width, height])
// - mode: 'rect' | 'polygon'
// - rect: Float32Array([x0, y0, x1, y1]) in screen pixels (for 'rect')
// - polygon: Float32Array of [x0,y0,x1,y1,...] in screen pixels (for 'polygon')

type SelectionMessage = {
  positions: Float32Array
  modelMatrix: Float32Array
  viewMatrix: Float32Array
  projMatrix: Float32Array
  viewport: Uint32Array
  mode: 'rect' | 'polygon'
  rect?: Float32Array
  polygon?: Float32Array
}

// Multiply 4x4 matrix by vec4
function mulMat4Vec4(out: Float32Array, m: Float32Array, x: number, y: number, z: number, w: number) {
  out[0] = m[0] * x + m[4] * y + m[8] * z + m[12] * w
  out[1] = m[1] * x + m[5] * y + m[9] * z + m[13] * w
  out[2] = m[2] * x + m[6] * y + m[10] * z + m[14] * w
  out[3] = m[3] * x + m[7] * y + m[11] * z + m[15] * w
}

// out = a * b (4x4)
function mulMat4(out: Float32Array, a: Float32Array, b: Float32Array) {
  const a00 = a[0], a01 = a[1], a02 = a[2], a03 = a[3]
  const a10 = a[4], a11 = a[5], a12 = a[6], a13 = a[7]
  const a20 = a[8], a21 = a[9], a22 = a[10], a23 = a[11]
  const a30 = a[12], a31 = a[13], a32 = a[14], a33 = a[15]

  let b0, b1, b2, b3

  b0 = b[0]; b1 = b[1]; b2 = b[2]; b3 = b[3]
  out[0] = a00 * b0 + a10 * b1 + a20 * b2 + a30 * b3
  out[1] = a01 * b0 + a11 * b1 + a21 * b2 + a31 * b3
  out[2] = a02 * b0 + a12 * b1 + a22 * b2 + a32 * b3
  out[3] = a03 * b0 + a13 * b1 + a23 * b2 + a33 * b3

  b0 = b[4]; b1 = b[5]; b2 = b[6]; b3 = b[7]
  out[4] = a00 * b0 + a10 * b1 + a20 * b2 + a30 * b3
  out[5] = a01 * b0 + a11 * b1 + a21 * b2 + a31 * b3
  out[6] = a02 * b0 + a12 * b1 + a22 * b2 + a32 * b3
  out[7] = a03 * b0 + a13 * b1 + a23 * b2 + a33 * b3

  b0 = b[8]; b1 = b[9]; b2 = b[10]; b3 = b[11]
  out[8] = a00 * b0 + a10 * b1 + a20 * b2 + a30 * b3
  out[9] = a01 * b0 + a11 * b1 + a21 * b2 + a31 * b3
  out[10] = a02 * b0 + a12 * b1 + a22 * b2 + a32 * b3
  out[11] = a03 * b0 + a13 * b1 + a23 * b2 + a33 * b3

  b0 = b[12]; b1 = b[13]; b2 = b[14]; b3 = b[15]
  out[12] = a00 * b0 + a10 * b1 + a20 * b2 + a30 * b3
  out[13] = a01 * b0 + a11 * b1 + a21 * b2 + a31 * b3
  out[14] = a02 * b0 + a12 * b1 + a22 * b2 + a32 * b3
  out[15] = a03 * b0 + a13 * b1 + a23 * b2 + a33 * b3
}

self.onmessage = (e: MessageEvent<SelectionMessage>) => {
  const { positions, modelMatrix, viewMatrix, projMatrix, viewport, mode, rect, polygon } = e.data
  const width = viewport[0]
  const height = viewport[1]

  let x0 = 0, y0 = 0, x1 = 0, y1 = 0
  if (mode === 'rect' && rect) {
    x0 = Math.min(rect[0], rect[2])
    y0 = Math.min(rect[1], rect[3])
    x1 = Math.max(rect[0], rect[2])
    y1 = Math.max(rect[1], rect[3])
  }

  const mv = new Float32Array(16)
  const mvp = new Float32Array(16)
  mulMat4(mv, viewMatrix, modelMatrix)
  mulMat4(mvp, projMatrix, mv)

  const out = new Float32Array(4)
  const count = positions.length / 3
  const mask = new Uint8Array(count)

  for (let i = 0; i < count; i++) {
    const idx = i * 3
    const x = positions[idx]
    const y = positions[idx + 1]
    const z = positions[idx + 2]

    mulMat4Vec4(out, mvp, x, y, z, 1)
    const w = out[3]
    if (w === 0) continue
    const ndcX = out[0] / w
    const ndcY = out[1] / w
    const ndcZ = out[2] / w

    if (ndcZ < -1 || ndcZ > 1) continue

    const sx = (ndcX * 0.5 + 0.5) * width
    const sy = (1 - (ndcY * 0.5 + 0.5)) * height

    if (mode === 'rect') {
      if (sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1) {
        mask[i] = 1
      }
    } else if (mode === 'polygon' && polygon && polygon.length >= 6) {
      // point-in-polygon (ray casting)
      let inside = false
      const n = polygon.length / 2
      let j = n - 1
      for (let k = 0; k < n; k++) {
        const xi = polygon[k * 2]
        const yi = polygon[k * 2 + 1]
        const xj = polygon[j * 2]
        const yj = polygon[j * 2 + 1]
        const intersect = ((yi > sy) !== (yj > sy)) && (sx < (xj - xi) * (sy - yi) / ((yj - yi) || 1e-8) + xi)
        if (intersect) inside = !inside
        j = k
      }
      if (inside) mask[i] = 1
    }
  }

  ;(self as any).postMessage(mask, [mask.buffer])
}



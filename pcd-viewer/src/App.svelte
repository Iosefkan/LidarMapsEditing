<script lang="ts">
  import PointCloudViewer from './components/PointCloudViewer.svelte'
  import { apiUploadPCD, apiListFiles, apiClean, type FileRecord, type CleanParams, apiSaveCleaned, apiSaveOriginal } from './lib/api'
  import { arraysToPCD, arraysToPCDBinary } from './lib/pcd'
  import Header from './components/Header.svelte'
  import Sidebar from './components/Sidebar.svelte'
  import Preloader from './components/Preloader.svelte'
  let viewerRef: any
  let fileInput: HTMLInputElement
  let busy = false
  let canUndo = false
  let isDirty = false
  let files: FileRecord[] = []
  let selectedId: string | null = null
  let selected: FileRecord | null = null
  let params: CleanParams = {
    grid: 0.45,
    q_low: 0.01,
    q_high: 0.98,
    smooth_cells: 13,
    h_min: 0.08,
    h_max: 4.5,
    min_len: 1.8,
    min_width: 1.0,
    max_width: 4.5,
    min_elong: 1.6,
    density_min: 3,
    use_hough: true,
    hough_theta_step: 5.0,
    hough_rho_bin: 0.5,
    hough_topk: 10,
    hough_min_len: 10,
    hough_min_w: 1.0,
    hough_max_w: 3.5,
    hough_dilate: 1,
  }

  let pointsCount = 0
  let defaultColor: [number, number, number] = [1,1,1]
  let backgroundColor: [number, number, number] = [0.043,0.043,0.043]
  let selectionColor: [number, number, number] = [1,0.8,0.2]
  let cleanedReady = false
  let currentView: 'original' | 'cleaned' | 'delta' | null = null
  let addMode = false
  let preloaderText: string = 'Загрузка…'

  async function refreshList() {
    files = await apiListFiles()
  }

  async function onFileChange(ev: Event) {
    const input = ev.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    // Show loader during local display and background upload
    busy = true
    // Immediately display the local file without blocking on upload
    await viewerRef.loadPCDFile(file)
    currentView = 'original'
    cleanedReady = false
    // Start upload in background
    ;(async () => {
      try {
        const rec = await apiUploadPCD(file)
        await refreshList()
        selectedId = rec.id
        selected = rec
        cleanedReady = !!rec.cleaned_url
      } catch (e) {
        // keep the locally loaded view; optionally report error later
        console.error(e)
      } finally {
        busy = false
        input.value = ''
      }
    })()
  }

  function onDeleteSelection() {
    if (currentView === 'delta') return
    viewerRef.deleteSelection()
  }
  function onUndo() {
    viewerRef?.undoLastDeletion?.()
  }
  function onReset() {
    viewerRef.resetView()
  }
  function onClear() {
    viewerRef.clear()
  }

  async function onSelectChange(ev: Event) {
    const id = (ev.target as HTMLSelectElement).value
    selectedId = id
    if (!id) { selected = null; viewerRef.clear(); cleanedReady=false; currentView=null; return }
    busy = true
    try {
      selected = files.find(f => f.id === id) || null
      if (selected?.original_url) {
        await viewerRef.loadPCDFromURL(selected.original_url)
        currentView = 'original'
      }
      cleanedReady = !!selected?.cleaned_url
    } finally {
      busy = false
    }
  }

  async function onLoadOriginal() {
    if (!selected?.original_url) return
    busy = true
    preloaderText = 'Загрузка…'
    try {
      await viewerRef.loadPCDFromURL(selected.original_url)
      currentView = 'original'
    } finally {
      busy = false
    }
  }
  async function onLoadCleaned() {
    if (!(cleanedReady && selected?.cleaned_url)) return
    busy = true
    preloaderText = 'Загрузка…'
    try {
      await viewerRef.loadPCDFromURL(selected.cleaned_url)
      currentView = 'cleaned'
      isDirty = false
    } finally {
      busy = false
    }
  }
  async function onLoadDelta() {
    if (!(cleanedReady && selected?.delta_url)) return
    busy = true
    preloaderText = 'Загрузка…'
    try {
      await viewerRef.loadPCDFromURL(selected.delta_url)
      currentView = 'delta'
      isDirty = false
    } finally {
      busy = false
    }
  }

  async function onRestoreSelected() {
    if (currentView !== 'delta' || !selected?.cleaned_url) return
    const subset = viewerRef.getSelectedSubset?.()
    if (!subset || subset.positions.length === 0) return
    busy = true
    preloaderText = 'Загрузка…'
    try {
      await viewerRef.loadPCDFromURL(selected.cleaned_url)
      currentView = 'cleaned'
      viewerRef.addPoints(subset.positions, subset.colors)
      isDirty = true
    } finally {
      busy = false
    }
  }

  async function onSave() {
    if (!selectedId || !isDirty || !currentView) return
    if (currentView === 'delta') return
    const data = viewerRef.getPointCloudData?.()
    if (!data) return
    // Prefer binary PCD to reduce file size; fall back to ASCII if needed
    let blob: Blob
    try {
      const bin = arraysToPCDBinary(data.positions)
      // Create a fresh ArrayBuffer to avoid SAB typing; copy into a new buffer
      const ab = new ArrayBuffer(bin.byteLength)
      new Uint8Array(ab).set(bin)
      blob = new Blob([ab], { type: 'application/octet-stream' })
    } catch {
      const pcdText = arraysToPCD(data.positions)
      blob = new Blob([pcdText], { type: 'application/octet-stream' })
    }
    busy = true
    preloaderText = 'Загрузка…'
    try {
      if (currentView === 'original') {
        await apiSaveOriginal(selectedId, blob)
      } else if (currentView === 'cleaned') {
        await apiSaveCleaned(selectedId, blob)
      }
      await refreshList()
      const updated = files.find(f => f.id === selectedId)
      if (updated) selected = updated
      if (currentView === 'original' && selected?.original_url) {
        await viewerRef.loadPCDFromURL(selected.original_url)
        // Saving original invalidates cleaned/delta on backend; reflect in UI
        cleanedReady = false
        currentView = 'original'
      } else if (currentView === 'cleaned' && selected?.cleaned_url) {
        await viewerRef.loadPCDFromURL(selected.cleaned_url)
      }
      isDirty = false
    } finally {
      busy = false
    }
  }

  async function onClean() {
    if (!selectedId) return
    busy = true
    preloaderText = 'Загрузка... Процесс может занять несколько минут'
    try {
      // Clear previous summary immediately so UI reflects a fresh run
      if (selected) { selected = { ...selected, summary: null } as any }
      const res = await apiClean(selectedId, params)
      // Optimistically update summary from response
      if (selected) { selected = { ...selected, summary: res.summary } as any }
      await refreshList()
      const updated = files.find(f => f.id === selectedId)
      if (updated) selected = updated
      cleanedReady = !!selected?.cleaned_url
      if (cleanedReady && selected?.cleaned_url) { await viewerRef.loadPCDFromURL(selected.cleaned_url); currentView='cleaned' }
    } finally {
      busy = false
      preloaderText = 'Загрузка…'
    }
  }

  refreshList()

  function onKeydown(ev: KeyboardEvent) {
    if (busy) { ev.preventDefault(); return }
    const isUndo = (ev.ctrlKey || ev.metaKey) && (ev.code === 'KeyZ' || ev.key.toLowerCase() === 'z')
    if (isUndo) {
      ev.preventDefault()
      onUndo()
    }
  }
</script>

<svelte:window on:keydown={onKeydown} />

<main class="grid grid-rows-[auto_1fr] h-full w-full text-neutral-800 dark:text-neutral-200">
  <Header {busy} {canUndo} {isDirty} {currentView}
    {addMode}
    onToggleAddMode={() => addMode = !addMode}
    onOpen={() => fileInput.click()}
    onReset={onReset}
    onClear={onClear}
    onUndo={onUndo}
    onDeleteSelection={onDeleteSelection}
    onRestore={onRestoreSelected}
    onSave={onSave}
    {files}
    {selectedId}
    setSelected={(id: string | null)=>onSelectChange({ target: { value: id } } as any)}
    onDeleteFile={async ()=>{ if (!selectedId) return; busy=true; try { const { apiDeleteFile } = await import('./lib/api'); await apiDeleteFile(selectedId); await refreshList(); selected=null; selectedId=null; cleanedReady=false; currentView=null; viewerRef.clear(); } finally { busy=false } }}
  />
  <input bind:this={fileInput} type="file" accept=".pcd" on:change={onFileChange} class="hidden" />
  <section class="min-h-0 grid grid-cols-[1fr_320px] gap-2">
    <PointCloudViewer bind:this={viewerRef} bind:canUndo={canUndo} bind:pointCount={pointsCount} bind:isDirty={isDirty} {defaultColor} {backgroundColor} {selectionColor} {addMode} {currentView} />
    <Sidebar {selectedId} {selected} {params} {busy} {currentView}
      onClean={onClean}
      onLoadOriginal={onLoadOriginal}
      onLoadCleaned={onLoadCleaned}
      onLoadDelta={onLoadDelta}
      canLoadCleaned={cleanedReady}
      canLoadDelta={cleanedReady}
      {pointsCount}
    >
      <div slot="defaultcolor" class="flex items-center gap-2">
        <input type="color" class="h-8 w-10" value={`#${defaultColor.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')}`} on:input={(e)=>{
          const hex=(e.target as HTMLInputElement).value.replace('#','')
          const r=parseInt(hex.slice(0,2),16)/255
          const g=parseInt(hex.slice(2,4),16)/255
          const b=parseInt(hex.slice(4,6),16)/255
          defaultColor = [r,g,b]
        }} />
        <span class="text-xs">{Math.round(defaultColor[0]*255)},{Math.round(defaultColor[1]*255)},{Math.round(defaultColor[2]*255)}</span>
      </div>
      <div slot="bgcolor" class="flex items-center gap-2">
        <input type="color" class="h-8 w-10" value={`#${backgroundColor.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')}`} on:input={(e)=>{
          const hex=(e.target as HTMLInputElement).value.replace('#','')
          const r=parseInt(hex.slice(0,2),16)/255
          const g=parseInt(hex.slice(2,4),16)/255
          const b=parseInt(hex.slice(4,6),16)/255
          backgroundColor = [r,g,b]
        }} />
        <span class="text-xs">{Math.round(backgroundColor[0]*255)},{Math.round(backgroundColor[1]*255)},{Math.round(backgroundColor[2]*255)}</span>
      </div>
      <div slot="selcolor" class="flex items-center gap-2">
        <input type="color" class="h-8 w-10" value={`#${selectionColor.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')}`} on:input={(e)=>{
          const hex=(e.target as HTMLInputElement).value.replace('#','')
          const r=parseInt(hex.slice(0,2),16)/255
          const g=parseInt(hex.slice(2,4),16)/255
          const b=parseInt(hex.slice(4,6),16)/255
          selectionColor = [r,g,b]
        }} />
        <span class="text-xs">{Math.round(selectionColor[0]*255)},{Math.round(selectionColor[1]*255)},{Math.round(selectionColor[2]*255)}</span>
      </div>
    </Sidebar>
    <Preloader visible={busy} text={preloaderText} />
  </section>
</main>

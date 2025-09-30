<script lang="ts">
  import { onMount } from 'svelte'
  export let selectedId: string | null = null
  export let params: any
  export let onClean: () => void
  export let canLoadCleaned = false
  export let canLoadDelta = false
  export let onLoadOriginal: () => void
  export let onLoadCleaned: () => void
  export let onLoadDelta: () => void
  export let selected: any
  export let busy = false
  export let pointsCount = 0
  export let currentView: 'original' | 'cleaned' | 'delta' | null = null
  
  function numberWithSpaces(x: number) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  let showInfo = false
  let infoText = ''
  let showParams = false
  onMount(async () => {
    try {
      const res = await fetch('/api/parameters')
      if (res.ok) infoText = await res.text()
    } catch {}
  })
</script>

<aside class="h-full overflow-y-auto border-l border-black/10 dark:border-white/10 p-3 bg-neutral-50 dark:bg-neutral-900/40 text-neutral-800 dark:text-white">
  <div class="space-y-3">
    <div class="text-sm">Точек: {numberWithSpaces(pointsCount)}</div>
    <div class="grid grid-cols-8 gap-2">
      <button
        class={"px-2 py-2 col-span-3 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-white " + (currentView==='original' ? '!bg-emerald-600 !text-white' : '')}
        on:click={onLoadOriginal}
        disabled={!selected?.original_url}
      >Оригинал</button>
      <button
        class={"px-2 py-2 col-span-3 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed " + (currentView==='cleaned' ? '!bg-emerald-600 !text-white' : '')}
        on:click={onLoadCleaned}
        disabled={!canLoadCleaned}
      >Очищенный</button>
      <button
        class={"px-2 py-2 col-span-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed " + (currentView==='delta' ? '!bg-emerald-600 !text-white' : '')}
        on:click={onLoadDelta}
        disabled={!canLoadDelta}
      >Дельта</button>
    </div>

    <div class="space-y-2">
      <div role="button" tabindex="0" class="w-full flex items-center justify-between px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-white" aria-expanded={showParams} on:click={() => showParams = !showParams} on:keydown={(e)=>{ const k=(e as KeyboardEvent).key; if(k==='Enter'||k===' '){ e.preventDefault(); showParams=!showParams } }}>
        <span class="text-sm text-neutral-700 dark:text-neutral-200">Параметры автоочистки</span>
        <span class="flex items-center gap-3">
          <button class="text-xs underline" type="button" on:click|stopPropagation={() => showInfo = true}>Информация</button>
          <span class="text-xs">{showParams ? '↑' : '↓'}</span>
        </span>
      </div>
      {#if showParams}
        <div class="grid grid-cols-2 gap-2 text-sm">
          <label>grid <input class="w-full" type="number" step="0.01" bind:value={params.grid}></label>
          <label>q_low <input class="w-full" type="number" step="0.01" bind:value={params.q_low}></label>
          <label>q_high <input class="w-full" type="number" step="0.01" bind:value={params.q_high}></label>
          <label>smooth_cells <input class="w-full" type="number" step="1" bind:value={params.smooth_cells}></label>
          <label>h_min <input class="w-full" type="number" step="0.01" bind:value={params.h_min}></label>
          <label>h_max <input class="w-full" type="number" step="0.01" bind:value={params.h_max}></label>
          <label>min_len <input class="w-full" type="number" step="0.01" bind:value={params.min_len}></label>
          <label>min_width <input class="w-full" type="number" step="0.01" bind:value={params.min_width}></label>
          <label>max_width <input class="w-full" type="number" step="0.01" bind:value={params.max_width}></label>
          <label>min_elong <input class="w-full" type="number" step="0.01" bind:value={params.min_elong}></label>
          <label>density_min <input class="w-full" type="number" step="1" bind:value={params.density_min}></label>
          <label class="col-span-2 flex items-center gap-2"><input type="checkbox" bind:checked={params.use_hough}> use_hough</label>
          <label>hough_theta_step <input class="w-full" type="number" step="0.1" bind:value={params.hough_theta_step}></label>
          <label>hough_rho_bin <input class="w-full" type="number" step="0.1" bind:value={params.hough_rho_bin}></label>
          <label>hough_topk <input class="w-full" type="number" step="1" bind:value={params.hough_topk}></label>
          <label>hough_min_len <input class="w-full" type="number" step="0.1" bind:value={params.hough_min_len}></label>
          <label>hough_min_w <input class="w-full" type="number" step="0.1" bind:value={params.hough_min_w}></label>
          <label>hough_max_w <input class="w-full" type="number" step="0.1" bind:value={params.hough_max_w}></label>
          <label>hough_dilate <input class="w-full" type="number" step="1" bind:value={params.hough_dilate}></label>
        </div>
      {/if}
      <button class="w-full px-3 py-2 rounded-md border border-white/10 bg-emerald-700/60 hover:bg-emerald-600" on:click={onClean} disabled={!selectedId || busy}>Запустить автоочистку</button>
    </div>

    <div class="space-y-1">
      <h3 class="text-sm text-neutral-400 dark:text-neutral-300">Цвет точек по умолчанию</h3>
      <div class="flex items-center gap-2">
        <slot name="defaultcolor"></slot>
      </div>
    </div>

    <div class="space-y-1">
      <h3 class="text-sm text-neutral-400 dark:text-neutral-300">Цвет фона</h3>
      <div class="flex items-center gap-2">
        <slot name="bgcolor"></slot>
      </div>
    </div>

    <div class="space-y-1">
      <h3 class="text-sm text-neutral-400 dark:text-neutral-300">Цвет выделенных точек</h3>
      <div class="flex items-center gap-2">
        <slot name="selcolor"></slot>
      </div>
    </div>

    {#if selected?.summary}
    <div class="space-y-1">
      <h3 class="text-sm text-neutral-400 dark:text-neutral-300">Параметры очистки</h3>
      <pre class="text-xs whitespace-pre-wrap bg-black/30 p-2 rounded">{JSON.stringify(selected.summary, null, 2)}</pre>
    </div>
    {/if}

    <div class="space-y-1">
      <h3 class="text-sm text-neutral-400 dark:text-neutral-300">Скачать файлы</h3>
      <div class="text-xs break-all">
        {#if selected?.original_url}
          <div>
            оригинал: <a class="text-sky-600 dark:text-sky-400 underline" href={selected.original_url} target="_blank">скачать</a>
          </div>
        {/if}
        {#if selected?.cleaned_url}
          <div>
            очищенный: <a class="text-sky-600 dark:text-sky-400 underline" href={selected.cleaned_url} target="_blank">скачать</a>
          </div>
        {/if}
        {#if selected?.delta_url}
          <div>
            дельта: <a class="text-sky-600 dark:text-sky-400 underline" href={selected.delta_url} target="_blank">скачать</a>
          </div>
        {/if}
      </div>
    </div>
  
  </div>

  {#if showInfo}
  <div class="fixed inset-0 bg-black/50 grid place-items-center z-50" role="dialog" aria-modal="true" tabindex="-1" on:click={() => showInfo=false} on:keydown={(e)=>{ if((e as KeyboardEvent).key==='Escape') showInfo=false }}>
    <section class="max-w-xl w-[90%] bg-white text-neutral-800 dark:bg-neutral-900 dark:text-white p-4 rounded-md border border-black/10 dark:border-white/10" role="document">
      <div class="flex justify-between items-center mb-2">
        <h3 class="text-lg">О параметрах</h3>
        <button class="text-base" type="button" on:click={() => showInfo=false}>×</button>
      </div>
      <pre class="text-sm whitespace-pre-wrap">{infoText}</pre>
    </section>
  </div>
  {/if}
</aside>

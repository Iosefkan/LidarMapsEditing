<script lang="ts">
  export let busy = false
  export let onOpen: () => void
  export let onReset: () => void
  export let onClear: () => void
  export let onUndo: () => void
  export let onDeleteSelection: () => void
  export let onRestore: () => void
  export let onSave: () => void
  export let canUndo = false
  export let isDirty = false
  export let currentView: 'original' | 'cleaned' | 'delta' | null = null
  export let addMode = false
  export let onToggleAddMode: () => void
  // file management
  export let files: any[] = []
  export let selectedId: string | null = null
  export let setSelected: (id: string | null) => void
  export let onDeleteFile: () => void

  import DeleteConfirmModal from './DeleteConfirmModal.svelte'
  let showDeleteConfirm = false
  let deleting = false
  async function confirmDelete() {
    if (!selectedId) return
    deleting = true
    try {
      await onDeleteFile?.()
      showDeleteConfirm = false
    } finally {
      deleting = false
    }
  }

  // Keep a local string value for the select binding to allow a disabled placeholder
  let selectedValue: string = ''
  $: selectedValue = selectedId ?? ''
</script>

<header class="grid grid-cols-4 gap-2 items-center px-3 py-2 border-b border-black/10 dark:border-white/10 bg-white/90 dark:bg-neutral-900/90 backdrop-blur text-neutral-800 dark:text-white">
  <div class="flex items-center gap-2">
    <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition" on:click={onOpen} disabled={busy}>
      {busy ? 'Загрузка…' : 'Загрузить PCD'}
    </button>
    <select class="px-2 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-white" on:change={(e)=>setSelected((e.target as HTMLSelectElement).value)} bind:value={selectedValue}>
      {#if !selectedId}
        <option value="" disabled>Выберите загруженный…</option>
      {/if}
      {#each files as f}
        <option value={f.id}>{f.filename}</option>
      {/each}
    </select>
    {#if selectedId}
      <button class="px-3 py-2 rounded-md border border-rose-500/30 text-rose-600 dark:text-rose-300 hover:bg-rose-500/10" on:click={() => showDeleteConfirm = true}>Удалить</button>
    {/if}
  </div>
  <div class="flex items-stretch">
    <span class="text-sm text-neutral-500 dark:text-neutral-300 text-center text-wrap">Мышь: вращение/пан/зум. Ctrl — прямоугольное выделение, Shift — лассо.</span>
  </div>
  <div class="flex justify-end items-stretch gap-2 col-span-2">
    {#if currentView !== 'delta'}
      <button class={"min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 " + (addMode ? 'bg-emerald-600 text-white' : 'bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition')} on:click={onToggleAddMode}>
        {addMode ? 'Добавление: ВКЛ' : 'Добавление: ВЫКЛ'}
      </button>
      <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition disabled:opacity-50 disabled:cursor-not-allowed" on:click={onDeleteSelection}>Удалить выделенное</button>
      <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition disabled:opacity-50" on:click={onUndo} disabled={!canUndo}>Отменить</button>
      <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition disabled:opacity-50 disabled:cursor-not-allowed" on:click={onSave} disabled={!isDirty || !currentView}>Сохранить</button>
    {:else}
      <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition disabled:opacity-50 disabled:cursor-not-allowed" on:click={onRestore}>Восстановить выделенное</button>
    {/if}
    <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition" on:click={onReset}>Сброс вида</button>
    <button class="min-w-28 px-3 py-2 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-gray-800 hover:border-emerald-400 transition" on:click={onClear}>Очистить сцену</button>
  </div>
</header>

<DeleteConfirmModal
  open={showDeleteConfirm}
  title="Удалить файл?"
  message="Это действие удалит PCD и все связанные данные. Операцию нельзя отменить."
  confirmText="Удалить"
  cancelText="Отмена"
  busy={deleting}
  onCancel={() => showDeleteConfirm=false}
  onConfirm={confirmDelete}
/>

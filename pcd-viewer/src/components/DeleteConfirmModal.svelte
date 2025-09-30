<script lang="ts">
  export let open = false
  export let title = 'Подтверждение'
  export let message = ''
  export let confirmText = 'ОК'
  export let cancelText = 'Отмена'
  export let busy = false
  export let onCancel: () => void
  export let onConfirm: () => void

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onCancel?.()
  }
</script>

{#if open}
<div class="fixed inset-0 bg-black/60 grid place-items-center z-50" role="dialog" aria-modal="true" tabindex="-1" on:keydown={onKeydown}>
  <section class="max-w-sm w-[90%] bg-white text-neutral-800 dark:bg-neutral-900 dark:text-white p-4 rounded-md border border-black/10 dark:border-white/10" role="document">
    <h3 class="text-xl mb-2">{title}</h3>
    {#if message}
      <p class="text-lg mb-3">{message}</p>
    {/if}
    <div class="flex justify-end gap-2">
      <button class="px-3 py-1.5 rounded-md border border-black/10 dark:border-white/10 bg-neutral-100 dark:bg-neutral-800" on:click={onCancel} disabled={busy}>{cancelText}</button>
      <button class="px-3 py-1.5 rounded-md border border-rose-500/30 text-rose-600 dark:text-rose-300 hover:bg-rose-500/10 disabled:opacity-50" on:click={onConfirm} disabled={busy}>
        {busy ? 'Удаление…' : confirmText}
      </button>
    </div>
  </section>
  
</div>
{/if}



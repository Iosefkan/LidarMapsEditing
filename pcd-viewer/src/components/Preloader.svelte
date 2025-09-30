<script lang="ts">
  export let visible = false
  export let text = 'Загрузка…'
</script>

<style>
  .overlay { position: fixed; inset: 0; display: grid; place-items: center; background: rgba(0,0,0,0.45); z-index: 1000 }
</style>

{#if visible}
<div class="overlay" role="dialog" aria-modal="true" aria-live="assertive">
  <div class="flex flex-col items-center gap-3 px-4 py-3 rounded-md border border-white/10 bg-neutral-900 text-white">
    <div class="h-10 w-10 rounded-full border-2 border-white/30 border-t-white animate-spin" aria-hidden="true"></div>
    <div class="text-sm">{text}</div>
  </div>
</div>
{/if}

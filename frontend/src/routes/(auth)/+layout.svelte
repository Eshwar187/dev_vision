<script lang="ts">
</script>

<div class="min-h-screen bg-slate-950 flex flex-col justify-center items-center p-4">
  <div class="w-full max-w-md space-y-6">
    <div class="text-center space-y-2">
      <div class="inline-flex h-12 w-12 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 items-center justify-center font-bold text-white text-xl shadow-lg shadow-cyan-500/20">
        DV
      </div>
      <h2 class="text-2xl font-bold tracking-tight text-white">DevVision AI</h2>
      <p class="text-xs text-slate-400">Multimodal AI Developer Copilot</p>
    </div>

    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-6 md:p-8 shadow-2xl backdrop-blur-sm">
      <slot />
    </div>

    <div class="text-center">
      <a href="/" class="text-xs text-slate-500 hover:text-slate-400 transition-colors">
        &larr; Back to Diagnostics Dashboard
      </a>
    </div>
  </div>
</div>
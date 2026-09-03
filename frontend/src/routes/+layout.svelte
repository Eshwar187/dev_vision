<script lang="ts">
  import "../app.css";
</script>

<div class="relative min-h-screen bg-slate-950 text-slate-100 flex flex-col">
  <!-- Top Navigation Header -->
  <header class="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-6 py-4 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="h-8 w-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20">
        DV
      </div>
      <div>
        <div class="flex items-center gap-2">
          <span class="font-semibold tracking-tight text-white">DevVision AI</span>
          <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-400 border border-cyan-800/50">
            Phase 0: Foundation
          </span>
        </div>
        <p class="text-xs text-slate-400">Multimodal Developer Copilot</p>
      </div>
    </div>

    <div class="flex items-center gap-4 text-xs">
      <div class="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 text-slate-300">
        <span class="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span>Modular Monolith</span>
      </div>
      <a
        href="https://github.com/Eshwar187/dev_vision"
        target="_blank"
        rel="noreferrer"
        class="text-slate-400 hover:text-slate-200 transition-colors"
      >
        GitHub Repository
      </a>
    </div>
  </header>

  <!-- Main Content Body -->
  <main class="flex-1 max-w-6xl w-full mx-auto p-6 md:p-8">
    <slot />
  </main>

  <!-- Footer -->
  <footer class="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
    <p>DevVision AI — Production Foundation. Built with SvelteKit, FastAPI, PostgreSQL, pgvector, Redis, and MinIO.</p>
  </footer>
</div>
<script lang="ts">
  import { Terminal, Shield, ArrowLeft } from "lucide-svelte";
</script>

<div class="min-h-screen bg-[#090d16] text-slate-100 font-sans flex flex-col justify-center items-center p-4 selection:bg-cyan-500 selection:text-white">
  <div class="w-full max-w-md space-y-6">
    <!-- Brand Title -->
    <div class="text-center space-y-2">
      <a href="/" class="inline-flex items-center gap-2.5 group">
        <div class="h-9 w-9 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-mono font-bold text-white text-sm shadow-sm shadow-cyan-500/30 group-hover:scale-105 transition-transform">
          DV
        </div>
        <span class="font-bold text-lg tracking-tight text-white group-hover:text-cyan-300 transition-colors">
          DevVision AI
        </span>
      </a>
      <p class="text-xs text-slate-400">Autonomous Codebase Intelligence & Engineering Copilot</p>
    </div>

    <!-- Auth Card Frame -->
    <div class="rounded-xl border border-slate-800/90 bg-slate-900/60 p-6 sm:p-7 shadow-2xl backdrop-blur-md">
      <slot />
    </div>

    <!-- Back Link -->
    <div class="text-center">
      <a
        href="/"
        class="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
      >
        <ArrowLeft class="w-3.5 h-3.5" />
        <span>Return to Platform Overview</span>
      </a>
    </div>
  </div>
</div>
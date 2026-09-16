<script lang="ts">
  import { onMount } from "svelte";
  import { api, type LiveStatus, type ReadyStatus, type SystemInfo, type ProbeResult } from "$lib/api/client";
  import { currentUser } from "$lib/stores/auth";
  import {
    Terminal,
    Shield,
    Cpu,
    GitBranch,
    Bot,
    ArrowRight,
    CheckCircle2,
    Lock,
    Zap,
    ExternalLink,
    Database,
    FileCode,
    Sparkles,
    Activity
  } from "lucide-svelte";

  let liveResult: ProbeResult<LiveStatus> | null = null;
  let readyResult: ProbeResult<ReadyStatus> | null = null;
  let systemResult: ProbeResult<SystemInfo> | null = null;
  let isChecking = false;

  async function refreshHealth() {
    isChecking = true;
    const [live, ready, system] = await Promise.all([
      api.checkLive(),
      api.checkReady(),
      api.getSystemInfo(),
    ]);
    liveResult = live;
    readyResult = ready;
    systemResult = system;
    isChecking = false;
  }

  onMount(() => {
    refreshHealth();
  });
</script>

<div class="min-h-screen bg-[#090d16] text-slate-100 font-sans selection:bg-cyan-500 selection:text-white flex flex-col">
  <!-- Public Landing Navigation Header -->
  <header class="sticky top-0 z-50 border-b border-slate-800/80 bg-[#090d16]/90 backdrop-blur-md px-6 py-3.5 flex items-center justify-between max-w-7xl w-full mx-auto">
    <div class="flex items-center gap-3">
      <div class="h-8 w-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-mono font-bold text-white text-xs shadow-sm shadow-cyan-500/30">
        DV
      </div>
      <div class="flex items-center gap-2">
        <span class="font-semibold text-sm tracking-tight text-white">DevVision AI</span>
        <span class="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/60">
          Self-Hosted
        </span>
      </div>
    </div>

    <!-- Right Actions -->
    <div class="flex items-center gap-4 text-xs">
      <a
        href="#architecture"
        class="text-slate-400 hover:text-slate-200 transition-colors hidden sm:inline"
      >
        Architecture
      </a>
      <a
        href="#features"
        class="text-slate-400 hover:text-slate-200 transition-colors hidden sm:inline"
      >
        Capabilities
      </a>
      <a
        href="https://github.com/Eshwar187/dev_vision"
        target="_blank"
        rel="noreferrer"
        class="text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1"
      >
        <span>GitHub</span>
        <ExternalLink class="w-3 h-3" />
      </a>

      {#if $currentUser}
        <a
          href="/app"
          class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs transition-colors shadow-sm shadow-cyan-600/20"
        >
          <span>Open Console</span>
          <ArrowRight class="w-3 h-3" />
        </a>
      {:else}
        <a
          href="/login"
          class="text-slate-300 hover:text-white transition-colors"
        >
          Sign In
        </a>
        <a
          href="/register"
          class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs transition-colors shadow-sm shadow-cyan-600/20"
        >
          <span>Get Started</span>
          <ArrowRight class="w-3 h-3" />
        </a>
      {/if}
    </div>
  </header>

  <!-- Hero Section -->
  <section class="max-w-5xl mx-auto px-6 pt-16 pb-12 text-center space-y-6">
    <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-300">
      <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
      <span class="font-mono text-cyan-400">Phase 7 Live:</span>
      <span>Multi-Language AST Codebase Intelligence</span>
    </div>

    <h1 class="text-3xl sm:text-5xl font-bold tracking-tight text-white max-w-3xl mx-auto leading-tight sm:leading-tight">
      Self-Hosted Codebase Intelligence & Grounded Code RAG
    </h1>

    <p class="text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
      Ingest software repositories securely, parse AST syntax trees across 6 languages, run 4-way hybrid retrieval, and query your codebase with deterministic line-level citations. <strong class="text-slate-200">Zero cloud AI exfiltration.</strong>
    </p>

    <!-- CTAs -->
    <div class="flex flex-wrap items-center justify-center gap-3 pt-4">
      {#if $currentUser}
        <a
          href="/app"
          class="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-all shadow-md shadow-cyan-600/20"
        >
          <span>Launch Dashboard Console</span>
          <ArrowRight class="w-4 h-4" />
        </a>
      {:else}
        <a
          href="/register"
          class="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-sm transition-all shadow-md shadow-cyan-600/20"
        >
          <span>Create Free Account</span>
          <ArrowRight class="w-4 h-4" />
        </a>
        <a
          href="/login"
          class="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-200 text-sm font-medium transition-all"
        >
          Sign In
        </a>
      {/if}
      <a
        href="/codebases"
        class="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 hover:text-slate-200 text-sm transition-all"
      >
        <GitBranch class="w-4 h-4 text-cyan-400" />
        <span>Explore Codebases</span>
      </a>
    </div>

    <!-- Cluster Status Banner -->
    <div class="pt-8 max-w-3xl mx-auto">
      <div class="rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 text-left font-mono text-xs space-y-3">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
          <div class="flex items-center gap-2 text-slate-300">
            <Activity class="w-3.5 h-3.5 text-emerald-400" />
            <span>Infrastructure Health Status</span>
          </div>
          <button
            type="button"
            on:click={refreshHealth}
            disabled={isChecking}
            class="text-[11px] text-cyan-400 hover:underline disabled:opacity-50"
          >
            {isChecking ? "Probing..." : "Refresh Probes"}
          </button>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
          <div>
            <span class="text-slate-500 block text-[10px]">API LIVENESS</span>
            <span class="{liveResult?.success ? 'text-emerald-400' : 'text-amber-400'} font-semibold">
              {liveResult?.success ? "ONLINE (200 OK)" : "STANDBY"}
            </span>
          </div>
          <div>
            <span class="text-slate-500 block text-[10px]">DATABASE ENGINE</span>
            <span class="text-slate-300">SQLAlchemy 2.0</span>
          </div>
          <div>
            <span class="text-slate-500 block text-[10px]">EMBEDDING REPO</span>
            <span class="text-slate-300">BAAI/bge-small</span>
          </div>
          <div>
            <span class="text-slate-500 block text-[10px]">AST GRAMMARS</span>
            <span class="text-cyan-400">Tree-sitter (6)</span>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Architectural Pillars Section -->
  <section id="features" class="max-w-6xl mx-auto px-6 py-12 space-y-6">
    <div class="text-center space-y-2">
      <h2 class="text-xl sm:text-2xl font-bold text-white tracking-tight">Engineered for Technical Rigor</h2>
      <p class="text-xs sm:text-sm text-slate-400 max-w-xl mx-auto">
        Built specifically for developer teams requiring uncompromising security, deterministic grounding, and complete infrastructure ownership.
      </p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
      <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
        <div class="h-8 w-8 rounded-lg bg-cyan-950/80 border border-cyan-800 flex items-center justify-center text-cyan-400">
          <Lock class="w-4 h-4" />
        </div>
        <h3 class="text-sm font-semibold text-white">100% Self-Hosted AI</h3>
        <p class="text-slate-400 leading-relaxed">
          Zero token telemetry sent to OpenAI, Anthropic, or external providers. Runs on self-hosted dense embeddings, cross-encoder rerankers, and local LLMs.
        </p>
      </div>

      <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
        <div class="h-8 w-8 rounded-lg bg-cyan-950/80 border border-cyan-800 flex items-center justify-center text-cyan-400">
          <GitBranch class="w-4 h-4" />
        </div>
        <h3 class="text-sm font-semibold text-white">Tree-sitter AST Parsing</h3>
        <p class="text-slate-400 leading-relaxed">
          Parses Python, JavaScript, TypeScript, Go, Rust, and Java into structured symbols, signature line ranges, and scope hierarchies before embedding.
        </p>
      </div>

      <div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800 space-y-3">
        <div class="h-8 w-8 rounded-lg bg-cyan-950/80 border border-cyan-800 flex items-center justify-center text-cyan-400">
          <Shield class="w-4 h-4" />
        </div>
        <h3 class="text-sm font-semibold text-white">Line-Level Verified Citations</h3>
        <p class="text-slate-400 leading-relaxed">
          Eliminates hallucinations with backend-verified citations. Real line coordinates are resolved by the server, accompanied by strict refusal handling.
        </p>
      </div>
    </div>
  </section>

  <!-- Technical Specs Table Section -->
  <section id="architecture" class="max-w-6xl mx-auto px-6 py-8 border-t border-slate-800/80">
    <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 class="text-xs font-semibold text-white uppercase tracking-wider">System Architecture & Pipeline Invariants</h3>
        <span class="text-[11px] font-mono text-cyan-400">Modular Monolith</span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
        <div class="p-3 rounded bg-slate-950 border border-slate-800/80 space-y-1">
          <div class="text-slate-500 text-[10px]">INGESTION DEFENSE</div>
          <div class="text-slate-200 font-semibold">Zip-Slip & Bomb Guards</div>
          <p class="text-slate-400 text-[10px]">Max ratio 20.0 • Device block</p>
        </div>
        <div class="p-3 rounded bg-slate-950 border border-slate-800/80 space-y-1">
          <div class="text-slate-500 text-[10px]">SECRET SCANNING</div>
          <div class="text-slate-200 font-semibold">Line-Preserving Redaction</div>
          <p class="text-slate-400 text-[10px]">Fatal drops for keys/certs</p>
        </div>
        <div class="p-3 rounded bg-slate-950 border border-slate-800/80 space-y-1">
          <div class="text-slate-500 text-[10px]">HYBRID RETRIEVAL</div>
          <div class="text-slate-200 font-semibold">RRF (k=60) + BGE Rerank</div>
          <p class="text-slate-400 text-[10px]">Dense 50 + Sparse 50 &rarr; Top 8</p>
        </div>
        <div class="p-3 rounded bg-slate-950 border border-slate-800/80 space-y-1">
          <div class="text-slate-500 text-[10px]">CONCURRENCY</div>
          <div class="text-slate-200 font-semibold">Active Pins + FOR UPDATE</div>
          <p class="text-slate-400 text-[10px]">Zero GC query corruption</p>
        </div>
      </div>
    </div>
  </section>

  <!-- Public Footer -->
  <footer class="mt-auto border-t border-slate-800/80 py-6 px-6 text-slate-500 text-xs">
    <div class="max-w-7xl w-full mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
      <div class="flex items-center gap-2">
        <div class="h-6 w-6 rounded bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-mono font-bold text-white text-[10px]">
          DV
        </div>
        <span>DevVision AI — Autonomous Multimodal Developer Copilot</span>
      </div>

      <div class="flex items-center gap-4 text-slate-400 text-xs">
        <a href="/login" class="hover:text-white transition-colors">Sign In</a>
        <a href="/register" class="hover:text-white transition-colors">Register</a>
        <a href="/app" class="hover:text-white transition-colors">Dashboard</a>
        <a href="/admin" class="hover:text-white transition-colors">Admin</a>
        <a href="https://github.com/Eshwar187/dev_vision" target="_blank" rel="noreferrer" class="hover:text-white transition-colors flex items-center gap-1">
          <span>GitHub</span>
          <ExternalLink class="w-3 h-3" />
        </a>
      </div>
    </div>
  </footer>
</div>
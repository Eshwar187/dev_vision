<script lang="ts">
  import { onMount } from "svelte";
  import { api, type LiveStatus, type ReadyStatus, type SystemInfo, type ProbeResult } from "$lib/api/client";

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

<div class="space-y-8">
  <!-- Hero Section -->
  <div class="rounded-xl border border-slate-800 bg-gradient-to-b from-slate-900/50 to-slate-950 p-6 md:p-8 shadow-xl">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-white">
          System Health & Architecture Status
        </h1>
        <p class="text-sm text-slate-400 mt-1">
          Real-time verification of SvelteKit frontend communicating with the FastAPI modular monolith backend.
        </p>
      </div>

      <button
        on:click={refreshHealth}
        disabled={isChecking}
        class="inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white transition-all shadow-md shadow-cyan-600/20 active:scale-95"
      >
        {#if isChecking}
          <svg class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          Probing Services...
        {:else}
          Run Health Diagnostics
        {/if}
      </button>
    </div>
  </div>

  <!-- Diagnostic Metrics Strip -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <!-- Liveness Probe -->
    <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">FastAPI Liveness</span>
        {#if liveResult?.success}
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
            <span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> LIVE
          </span>
        {:else}
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-950 text-rose-400 border border-rose-800">
            <span class="h-1.5 w-1.5 rounded-full bg-rose-400"></span> OFFLINE
          </span>
        {/if}
      </div>
      <div class="mt-3">
        <div class="text-xl font-bold text-white">/health/live</div>
        <p class="text-xs text-slate-400 mt-1">
          Latency: <span class="font-mono text-cyan-400">{liveResult?.latencyMs ?? 0} ms</span>
        </p>
        {#if liveResult?.requestId}
          <p class="text-[11px] font-mono text-slate-500 truncate mt-1">
            ID: {liveResult.requestId}
          </p>
        {/if}
      </div>
    </div>

    <!-- Readiness Probe -->
    <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Stack Readiness</span>
        {#if readyResult?.data?.status === "healthy"}
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
            <span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> READY
          </span>
        {:else}
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-950 text-amber-400 border border-amber-800">
            <span class="h-1.5 w-1.5 rounded-full bg-amber-400"></span> DEGRADED
          </span>
        {/if}
      </div>
      <div class="mt-3">
        <div class="text-xl font-bold text-white">/health/ready</div>
        <p class="text-xs text-slate-400 mt-1">
          Deep check: <span class="text-slate-300 font-medium">{readyResult?.data?.status ?? "unverified"}</span>
        </p>
        {#if readyResult?.requestId}
          <p class="text-[11px] font-mono text-slate-500 truncate mt-1">
            ID: {readyResult.requestId}
          </p>
        {/if}
      </div>
    </div>

    <!-- System Version Info -->
    <div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">API Contract</span>
        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800 text-slate-300">
          v1.0
        </span>
      </div>
      <div class="mt-3">
        <div class="text-xl font-bold text-white">/api/v1/system/info</div>
        <p class="text-xs text-slate-400 mt-1">
          Env: <span class="font-mono text-cyan-400">{systemResult?.data?.environment ?? "development"}</span>
        </p>
        <p class="text-[11px] font-mono text-slate-500 mt-1">
          FastAPI + Uvicorn ASGI
        </p>
      </div>
    </div>
  </div>

  <!-- Architectural Pillars Grid -->
  <div class="space-y-4">
    <h2 class="text-lg font-semibold text-white tracking-tight">Phase 0 Infrastructure Pillars</h2>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- PostgreSQL 16 -->
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 font-medium text-white">
            <span class="text-cyan-400 font-mono">01.</span> PostgreSQL 16
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {readyResult?.data?.checks.database === "healthy" ? "CONNECTED" : "AWAITING DB DOCKER"}
          </span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Primary transactional database configured with async SQLAlchemy 2.0 (<code class="text-cyan-300">asyncpg</code>), UUIDv4 primary keys, and UTC timestamps.
        </p>
        <div class="text-xs font-mono text-slate-500 bg-slate-950 p-2.5 rounded border border-slate-800/80">
          Port: 5432 &bull; Pool: 10/20 &bull; Driver: asyncpg
        </div>
      </div>

      <!-- pgvector Extension -->
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 font-medium text-white">
            <span class="text-cyan-400 font-mono">02.</span> pgvector Extension
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {readyResult?.data?.checks.pgvector === "installed" ? "INSTALLED" : "READY TO MOUNT"}
          </span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Enabled for future high-dimensional vector embeddings and approximate nearest neighbor search via HNSW indexes. Dimension flexible for Phase 1.
        </p>
        <div class="text-xs font-mono text-slate-500 bg-slate-950 p-2.5 rounded border border-slate-800/80">
          Image: pgvector/pgvector:pg16 &bull; Type: Vector (dynamic)
        </div>
      </div>

      <!-- Redis 7 -->
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 font-medium text-white">
            <span class="text-cyan-400 font-mono">03.</span> Redis 7
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {readyResult?.data?.checks.redis === "healthy" ? "CONNECTED" : "AWAITING REDIS DOCKER"}
          </span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          In-memory store configured for sub-millisecond caching, rate limiting, and task message broker foundation for future background workers.
        </p>
        <div class="text-xs font-mono text-slate-500 bg-slate-950 p-2.5 rounded border border-slate-800/80">
          Port: 6379 &bull; Driver: redis.asyncio &bull; Pool: 20 max
        </div>
      </div>

      <!-- MinIO S3 Object Storage -->
      <div class="rounded-lg border border-slate-800 bg-slate-900/40 p-5 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 font-medium text-white">
            <span class="text-cyan-400 font-mono">04.</span> MinIO / S3 Storage
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {readyResult?.data?.checks.storage === "healthy" ? "CONNECTED" : "AWAITING MINIO DOCKER"}
          </span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          S3-compatible object storage abstraction for documents, code archives, media, and artifacts. Configured with a single private bucket.
        </p>
        <div class="text-xs font-mono text-slate-500 bg-slate-950 p-2.5 rounded border border-slate-800/80">
          Bucket: devvision-local &bull; Ports: 9000 (API) / 9001 (Console)
        </div>
      </div>
    </div>
  </div>

  <!-- ADR Quick Reference -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/30 p-5 space-y-3">
    <h3 class="text-sm font-semibold text-white">Phase 0 Architectural Decisions (ADRs)</h3>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
      <div class="p-3 rounded bg-slate-950/60 border border-slate-800/60">
        <div class="font-medium text-cyan-400">ADR 0001</div>
        <div class="text-slate-300 mt-1">Modular Monolith</div>
        <div class="text-[11px] text-slate-500 mt-1">Single repo, domain modules, async decoupling.</div>
      </div>
      <div class="p-3 rounded bg-slate-950/60 border border-slate-800/60">
        <div class="font-medium text-cyan-400">ADR 0002</div>
        <div class="text-slate-300 mt-1">SvelteKit + FastAPI</div>
        <div class="text-[11px] text-slate-500 mt-1">Svelte 5 reactivity + Python AI/ML ecosystem.</div>
      </div>
      <div class="p-3 rounded bg-slate-950/60 border border-slate-800/60">
        <div class="font-medium text-cyan-400">ADR 0003</div>
        <div class="text-slate-300 mt-1">PostgreSQL + pgvector</div>
        <div class="text-[11px] text-slate-500 mt-1">Relational integrity + native vector storage.</div>
      </div>
      <div class="p-3 rounded bg-slate-950/60 border border-slate-800/60">
        <div class="font-medium text-cyan-400">ADR 0004</div>
        <div class="text-slate-300 mt-1">S3-Compatible Storage</div>
        <div class="text-[11px] text-slate-500 mt-1">MinIO locally, seamless AWS S3 in production.</div>
      </div>
    </div>
  </div>
</div>
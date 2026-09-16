<script lang="ts">
  import { onMount } from "svelte";
  import { currentUser } from "$lib/stores/auth";
  import { activeWorkspace, workspaces } from "$lib/stores/workspace";
  import { api } from "$lib/api/client";
  import {
    GitBranch,
    Bot,
    FileText,
    Shield,
    Users,
    Activity,
    ArrowUpRight,
    Search,
    Code2,
    CheckCircle2,
    Sparkles,
    Terminal,
    Layers,
    Clock,
    Cpu
  } from "lucide-svelte";
  import type { CodebaseItem, DocumentItem } from "$lib/api/types";

  let recentCodebases: CodebaseItem[] = [];
  let recentDocs: DocumentItem[] = [];
  let isLoading = false;
  let systemHealth: any = null;

  $: ws = $activeWorkspace;

  onMount(async () => {
    if (ws?.id) {
      await loadDashboardData(ws.id);
    }
  });

  $: if (ws?.id) {
    loadDashboardData(ws.id);
  }

  async function loadDashboardData(wsId: string) {
    isLoading = true;
    const [codebasesRes, docsRes, healthRes] = await Promise.all([
      api.listCodebases(wsId),
      api.listDocuments(wsId, 5),
      api.checkReady(),
    ]);
    isLoading = false;

    if (codebasesRes.success && codebasesRes.data) {
      recentCodebases = codebasesRes.data.items.slice(0, 4);
    }
    if (docsRes.success && docsRes.data) {
      recentDocs = docsRes.data.items.slice(0, 4);
    }
    if (healthRes.success && healthRes.data) {
      systemHealth = healthRes.data;
    }
  }
</script>

<div class="space-y-6">
  <!-- Top Welcome Strip -->
  <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800/80 pb-6">
    <div>
      <div class="flex items-center gap-2 mb-1">
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 uppercase">
          <Terminal class="w-3 h-3" />
          DevVision AI Console
        </span>
        <span class="text-slate-500 text-xs font-mono">•</span>
        <span class="text-xs text-slate-400 font-mono">Tenant: {ws?.name || "No Workspace"}</span>
      </div>
      <h1 class="text-2xl font-bold tracking-tight text-white">
        Developer Overview
      </h1>
      <p class="text-xs text-slate-400 mt-1">
        Connected as <span class="text-slate-200 font-medium">{$currentUser?.display_name || $currentUser?.email}</span> with role <span class="text-cyan-400 font-mono capitalize">{ws?.role || "Member"}</span>.
      </p>
    </div>

    <!-- Fast Action Buttons -->
    <div class="flex items-center gap-2">
      <a
        href="/codebases"
        class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors shadow-sm shadow-cyan-600/20"
      >
        <GitBranch class="w-3.5 h-3.5" />
        <span>Index Codebase</span>
      </a>
      <a
        href="/rag"
        class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-slate-200 text-xs font-medium transition-colors"
      >
        <Bot class="w-3.5 h-3.5 text-cyan-400" />
        <span>Open Copilot</span>
      </a>
    </div>
  </div>

  <!-- Primary Metric Highlights -->
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
    <!-- Codebases Stat -->
    <a
      href="/codebases"
      class="group p-4 rounded-xl bg-slate-900/50 border border-slate-800/90 hover:border-slate-700 transition-all block"
    >
      <div class="flex items-center justify-between text-slate-400 mb-2">
        <span class="font-medium text-[11px] uppercase tracking-wider">Codebases</span>
        <GitBranch class="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
      </div>
      <div class="text-2xl font-bold text-white font-mono">{recentCodebases.length}</div>
      <p class="text-[11px] text-slate-400 mt-1 flex items-center justify-between">
        <span>AST-parsed repositories</span>
        <ArrowUpRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-400 transition-colors" />
      </p>
    </a>

    <!-- Documents Stat -->
    <a
      href="/documents"
      class="group p-4 rounded-xl bg-slate-900/50 border border-slate-800/90 hover:border-slate-700 transition-all block"
    >
      <div class="flex items-center justify-between text-slate-400 mb-2">
        <span class="font-medium text-[11px] uppercase tracking-wider">Documents</span>
        <FileText class="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
      </div>
      <div class="text-2xl font-bold text-white font-mono">{recentDocs.length}</div>
      <p class="text-[11px] text-slate-400 mt-1 flex items-center justify-between">
        <span>Indexed specs & architecture</span>
        <ArrowUpRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-400 transition-colors" />
      </p>
    </a>

    <!-- RAG Intelligence Stat -->
    <a
      href="/rag"
      class="group p-4 rounded-xl bg-slate-900/50 border border-slate-800/90 hover:border-slate-700 transition-all block"
    >
      <div class="flex items-center justify-between text-slate-400 mb-2">
        <span class="font-medium text-[11px] uppercase tracking-wider">Retriever Mode</span>
        <Layers class="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
      </div>
      <div class="text-base font-bold text-white">4-Way Hybrid RRF</div>
      <p class="text-[11px] text-slate-400 mt-1 flex items-center justify-between">
        <span>Dense + Sparse + Reranker</span>
        <ArrowUpRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-400 transition-colors" />
      </p>
    </a>

    <!-- Tenant Isolation Stat -->
    <a
      href="/admin"
      class="group p-4 rounded-xl bg-slate-900/50 border border-slate-800/90 hover:border-slate-700 transition-all block"
    >
      <div class="flex items-center justify-between text-slate-400 mb-2">
        <span class="font-medium text-[11px] uppercase tracking-wider">Isolation Barrier</span>
        <Shield class="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
      </div>
      <div class="text-base font-bold text-emerald-400">Strict Multi-Tenant</div>
      <p class="text-[11px] text-slate-400 mt-1 flex items-center justify-between">
        <span>IDOR & CSRF protected</span>
        <ArrowUpRight class="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-400 transition-colors" />
      </p>
    </a>
  </div>

  <!-- Main 2-Column Split: Active Codebases & Documents -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
    <!-- Left Column: Indexed Repositories -->
    <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center gap-2">
          <GitBranch class="w-4 h-4 text-cyan-400" />
          <h3 class="text-xs font-semibold text-white uppercase tracking-wider">Codebases in Workspace</h3>
        </div>
        <a href="/codebases" class="text-xs text-cyan-400 hover:text-cyan-300 font-medium">View all &rarr;</a>
      </div>

      {#if recentCodebases.length > 0}
        <div class="space-y-2.5">
          {#each recentCodebases as cb}
            <a
              href="/codebases/{cb.id}"
              class="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/80 hover:border-cyan-500/50 transition-all flex items-center justify-between group block"
            >
              <div class="space-y-1 min-w-0 pr-3">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-white group-hover:text-cyan-300 transition-colors truncate">
                    {cb.name}
                  </span>
                  <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                    {cb.default_branch}
                  </span>
                </div>
                <div class="text-[11px] text-slate-500 font-mono truncate">
                  {cb.repository_url || "Local archive upload"}
                </div>
              </div>

              <div class="text-right flex-shrink-0">
                {#if cb.is_indexed}
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
                    <CheckCircle2 class="w-3 h-3" /> Indexed
                  </span>
                {:else}
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-amber-950/80 text-amber-400 border border-amber-800/60">
                    <Clock class="w-3 h-3" /> Pending
                  </span>
                {/if}
              </div>
            </a>
          {/each}
        </div>
      {:else}
        <div class="text-center py-8 space-y-2">
          <Code2 class="w-8 h-8 text-slate-600 mx-auto" />
          <p class="text-xs text-slate-400">No codebases indexed in this workspace yet.</p>
          <a
            href="/codebases"
            class="inline-block text-xs font-medium text-cyan-400 hover:text-cyan-300 pt-1"
          >
            + Upload repository .zip
          </a>
        </div>
      {/if}
    </div>

    <!-- Right Column: Documents & Grounding Knowledge -->
    <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center gap-2">
          <FileText class="w-4 h-4 text-cyan-400" />
          <h3 class="text-xs font-semibold text-white uppercase tracking-wider">Knowledge Base Documents</h3>
        </div>
        <a href="/documents" class="text-xs text-cyan-400 hover:text-cyan-300 font-medium">View all &rarr;</a>
      </div>

      {#if recentDocs.length > 0}
        <div class="space-y-2.5">
          {#each recentDocs as doc}
            <div class="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
              <div class="space-y-1 min-w-0 pr-3">
                <div class="text-xs font-semibold text-slate-200 truncate">{doc.original_filename}</div>
                <div class="text-[11px] text-slate-500 font-mono">
                  {(doc.file_size / 1024).toFixed(1)} KB • {doc.mime_type}
                </div>
              </div>

              <span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono capitalize border {doc.status === 'ready' ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60' : doc.status === 'processing' ? 'bg-cyan-950/80 text-cyan-400 border-cyan-800/60' : 'bg-slate-800 text-slate-400 border-slate-700'}">
                {doc.status}
              </span>
            </div>
          {/each}
        </div>
      {:else}
        <div class="text-center py-8 space-y-2">
          <FileText class="w-8 h-8 text-slate-600 mx-auto" />
          <p class="text-xs text-slate-400">No documents uploaded to this workspace yet.</p>
          <a
            href="/documents"
            class="inline-block text-xs font-medium text-cyan-400 hover:text-cyan-300 pt-1"
          >
            + Upload PDF, DOCX, or Markdown
          </a>
        </div>
      {/if}
    </div>
  </div>

  <!-- Operational Health Strip -->
  <div class="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
    <div class="flex items-center gap-3">
      <div class="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
      <div class="font-medium text-slate-300">Cluster Status: <span class="text-emerald-400 font-mono">READY</span></div>
      <span class="text-slate-600 hidden sm:inline">•</span>
      <div class="text-slate-400 hidden sm:inline">Self-Hosted BAAI/bge Embeddings & Reranker Loaded</div>
    </div>

    <div class="flex items-center gap-3 font-mono text-[11px] text-slate-400">
      <span>Driver: <span class="text-cyan-400">SQLAlchemy 2.0</span></span>
      <span>•</span>
      <a href="/admin" class="text-slate-300 hover:text-white underline">Admin Diagnostic Console &rarr;</a>
    </div>
  </div>
</div>

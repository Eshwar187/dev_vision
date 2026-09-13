<script lang="ts">
  import { onMount } from "svelte";
  import { activeWorkspace } from "$lib/stores/workspace";
  import { api } from "$lib/api/client";
  import type { RagCitation, RagHistoryItem, RagQueryResponse } from "$lib/api/types";

  let queryText = "";
  let topK = 5;
  let isSubmitting = false;
  let currentResponse: RagQueryResponse | null = null;
  let historyItems: RagHistoryItem[] = [];
  let isLoadingHistory = false;
  let errorMessage: string | null = null;

  // Flyout / Drawer state
  let selectedCitation: RagCitation | null = null;
  let isDrawerOpen = false;

  // Operational resilience UI state
  let rateLimitRetryAfter: number | null = null;
  let isTimeoutError = false;
  let lastSubmittedQuery = "";

  onMount(async () => {
    if ($activeWorkspace) {
      await loadHistory();
    }
  });

  $: if ($activeWorkspace) {
    loadHistory();
  }

  async function loadHistory() {
    if (!$activeWorkspace) return;
    isLoadingHistory = true;
    errorMessage = null;
    const res = await api.getRagHistory($activeWorkspace.id, 20);
    if (res.success && res.data) {
      historyItems = res.data.items;
    } else {
      errorMessage = res.error || "Failed to load RAG query history.";
    }
    isLoadingHistory = false;
  }

  async function handleQuerySubmit() {
    if (!queryText.trim() || isSubmitting || !$activeWorkspace) return;
    const targetWorkspaceId = $activeWorkspace.id;
    const currentQuery = queryText.trim();
    lastSubmittedQuery = currentQuery;
    isSubmitting = true;
    errorMessage = null;
    rateLimitRetryAfter = null;
    isTimeoutError = false;

    const res = await api.executeRagQuery(targetWorkspaceId, currentQuery, topK);
    if (res.success && res.data) {
      // Prevent stale response clobbering if user switched active workspace while query was in flight
      if ($activeWorkspace?.id === targetWorkspaceId) {
        currentResponse = res.data;
        historyItems = [
          {
            id: res.data.query_id,
            workspace_id: targetWorkspaceId,
            user_id: null,
            query_text: res.data.query_text,
            answer: res.data.answer,
            has_unverified_claims: res.data.has_unverified_claims,
            retrieval_chunks_count: res.data.citations.length,
            processing_time_ms: res.data.processing_time_ms,
            created_at: res.data.created_at,
            citations: res.data.citations,
          },
          ...historyItems,
        ];
      }
      queryText = "";
    } else {
      if ($activeWorkspace?.id === targetWorkspaceId) {
        if (res.statusCode === 429) {
          rateLimitRetryAfter = res.retryAfterSeconds || 30;
          errorMessage = `Rate limit exceeded (30 queries/minute). Please wait ${rateLimitRetryAfter}s before retrying.`;
        } else if (res.statusCode === 504) {
          isTimeoutError = true;
          errorMessage = "Query timed out. The local LLM inference took longer than 60 seconds.";
        } else if (res.statusCode === 0) {
          errorMessage = "DevVision backend service is unreachable. Ensure the FastAPI and LLM daemons are running.";
        } else {
          errorMessage = res.error || "RAG query failed. Please check local LLM daemon.";
        }
      }
    }
    isSubmitting = false;
  }

  function retryLastQuery() {
    if (lastSubmittedQuery) {
      queryText = lastSubmittedQuery;
      handleQuerySubmit();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      handleQuerySubmit();
    }
  }

  function openCitationDrawer(citation: RagCitation) {
    selectedCitation = citation;
    isDrawerOpen = true;
  }

  function closeCitationDrawer() {
    isDrawerOpen = false;
    selectedCitation = null;
  }
</script>

<svelte:head>
  <title>RAG Assistant - DevVision AI</title>
</svelte:head>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div>
      <h1 class="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
        RAG Assistant
        <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800">
          100% Self-Hosted
        </span>
      </h1>
      <p class="text-sm text-slate-400 mt-1">
        Ask technical questions across workspace documentation with dense + sparse retrieval and verifiable citations.
      </p>
    </div>
  </div>

  {#if !$activeWorkspace}
    <div class="rounded-xl border border-amber-500/20 bg-amber-500/10 p-6 text-center">
      <h3 class="text-sm font-semibold text-amber-300">No Workspace Selected</h3>
      <p class="text-xs text-amber-200/80 mt-1">Please select or create a workspace to query indexed documentation.</p>
    </div>
  {:else}
    <!-- Rate Limit Exceeded Alert -->
    {#if rateLimitRetryAfter !== null}
      <div class="p-4 rounded-xl bg-amber-950/40 border border-amber-800/80 text-amber-300 text-sm flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="px-2 py-0.5 text-xs font-semibold bg-amber-900/60 rounded text-amber-200 border border-amber-700/50">429 RATE LIMIT</span>
          <span>{errorMessage}</span>
        </div>
        <button on:click={() => { rateLimitRetryAfter = null; errorMessage = null; }} class="text-xs text-amber-400 hover:underline">Dismiss</button>
      </div>
    {:else if isTimeoutError}
      <!-- Gateway Timeout Alert -->
      <div class="p-4 rounded-xl bg-orange-950/40 border border-orange-800/80 text-orange-300 text-sm flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="px-2 py-0.5 text-xs font-semibold bg-orange-900/60 rounded text-orange-200 border border-orange-700/50">504 TIMEOUT</span>
          <span>{errorMessage}</span>
        </div>
        <div class="flex items-center gap-3">
          <button on:click={retryLastQuery} class="text-xs px-2.5 py-1 bg-orange-900/80 hover:bg-orange-800 text-orange-200 rounded-md font-medium border border-orange-700">
            Retry Query
          </button>
          <button on:click={() => { isTimeoutError = false; errorMessage = null; }} class="text-xs text-orange-400 hover:underline">Dismiss</button>
        </div>
      </div>
    {:else if errorMessage}
      <!-- General Error Alert -->
      <div class="p-4 rounded-xl bg-rose-950/40 border border-rose-800/80 text-rose-300 text-sm flex items-center justify-between">
        <span>{errorMessage}</span>
        <button on:click={() => (errorMessage = null)} class="text-xs text-rose-400 hover:underline">Dismiss</button>
      </div>
    {/if}

    <!-- Query Input Area -->
    <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-sm">
      <div class="space-y-3">
        <label for="rag-query" class="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Query Prompt
        </label>
        <textarea
          id="rag-query"
          bind:value={queryText}
          on:keydown={handleKeydown}
          placeholder="Ask anything about your architecture, requirements, or code standards... (Ctrl+Enter to submit)"
          rows="3"
          disabled={isSubmitting}
          class="w-full rounded-xl bg-slate-950 border border-slate-800 p-3.5 text-sm text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-all resize-none disabled:opacity-50"
        ></textarea>

        <div class="flex items-center justify-between pt-1">
          <div class="flex items-center gap-4 text-xs text-slate-400">
            <span class="hidden sm:inline">Press <kbd class="px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 text-[10px]">Ctrl</kbd> + <kbd class="px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 text-[10px]">Enter</kbd></span>
            <div class="flex items-center gap-1.5">
              <label for="top-k-select">Passages (Top-K):</label>
              <select
                id="top-k-select"
                bind:value={topK}
                class="bg-slate-950 border border-slate-800 rounded px-2 py-0.5 text-xs text-slate-200"
              >
                <option value={3}>3</option>
                <option value={5}>5</option>
                <option value={10}>10</option>
              </select>
            </div>
          </div>

          <button
            on:click={handleQuerySubmit}
            disabled={isSubmitting || !queryText.trim()}
            class="px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs shadow-lg shadow-cyan-600/20 disabled:opacity-50 transition-all flex items-center gap-2"
          >
            {#if isSubmitting}
              <div class="h-3 w-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              <span>Synthesizing...</span>
            {:else}
              <span>Ask Assistant</span>
            {/if}
          </button>
        </div>
      </div>
    </div>

    <!-- Active / Latest Response Card -->
    {#if currentResponse}
      <div class="rounded-2xl border border-cyan-800/40 bg-slate-900/80 p-6 shadow-2xl relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold uppercase tracking-wider text-cyan-400">Answer</span>
            {#if currentResponse.has_unverified_claims}
              <span class="text-[10px] bg-amber-950/80 text-amber-300 border border-amber-700 px-2 py-0.5 rounded-full">
                Contains Unverified Claims
              </span>
            {:else}
              <span class="text-[10px] bg-emerald-950/80 text-emerald-300 border border-emerald-700 px-2 py-0.5 rounded-full">
                Fully Grounded
              </span>
            {/if}
          </div>
          <span class="text-xs text-slate-500">{currentResponse.processing_time_ms} ms</span>
        </div>

        <div class="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">
          {currentResponse.answer}
        </div>

        <!-- Citation Badges -->
        {#if currentResponse.citations.length > 0}
          <div class="mt-6 pt-4 border-t border-slate-800/80">
            <div class="text-xs font-semibold text-slate-400 mb-3">Sources & Provenance:</div>
            <div class="flex flex-wrap gap-2">
              {#each currentResponse.citations as cit}
                <button
                  on:click={() => openCitationDrawer(cit)}
                  class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-700/80 hover:border-cyan-500/80 transition-all text-xs text-left group"
                >
                  <span class="h-4 w-4 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-700 flex items-center justify-center font-bold text-[10px]">
                    {cit.citation_marker}
                  </span>
                  <span class="text-slate-300 group-hover:text-white truncate max-w-[200px]">
                    {cit.document_name}
                  </span>
                  {#if cit.page_number}
                    <span class="text-[10px] text-slate-500">p.{cit.page_number}</span>
                  {/if}
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Historical Queries Section -->
    <div class="space-y-4 pt-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Query History ({historyItems.length})
        </h2>
        <span class="text-xs text-slate-500">Retained for 90 days</span>
      </div>

      {#if isLoadingHistory}
        <div class="py-8 text-center text-xs text-slate-500">Loading history...</div>
      {:else if historyItems.length === 0}
        <div class="py-8 text-center text-xs text-slate-500">No previous queries in this workspace.</div>
      {:else}
        <div class="space-y-3">
          {#each historyItems as item}
            <div class="rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 hover:border-slate-700 transition-colors">
              <div class="flex items-center justify-between text-xs text-slate-400 mb-2">
                <span class="font-semibold text-slate-200 truncate max-w-[80%]">"{item.query_text}"</span>
                <span>{new Date(item.created_at).toLocaleDateString()}</span>
              </div>
              <p class="text-xs text-slate-300 line-clamp-3 leading-relaxed mb-3">{item.answer}</p>
              {#if item.citations.length > 0}
                <div class="flex flex-wrap gap-1.5 pt-2 border-t border-slate-800/50">
                  {#each item.citations as cit}
                    <button
                      on:click={() => openCitationDrawer(cit)}
                      class="text-[11px] px-2 py-0.5 rounded bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-cyan-300 transition-colors flex items-center gap-1"
                    >
                      <span class="text-cyan-400">[{cit.citation_marker}]</span>
                      <span class="truncate max-w-[150px]">{cit.document_name}</span>
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- Flyout / Citation Drawer -->
{#if isDrawerOpen && selectedCitation}
  <div class="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs">
    <!-- Backdrop dismiss -->
    <button
      on:click={closeCitationDrawer}
      aria-label="Close drawer backdrop"
      class="flex-1 cursor-default"
    ></button>

    <!-- Drawer Panel -->
    <div class="w-full max-w-md bg-slate-900 border-l border-slate-800 h-full p-6 flex flex-col shadow-2xl overflow-y-auto">
      <div class="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
        <div class="flex items-center gap-2">
          <span class="h-6 w-6 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-700 flex items-center justify-center font-bold text-xs">
            {selectedCitation.citation_marker}
          </span>
          <h3 class="text-sm font-semibold text-white truncate max-w-[280px]">
            {selectedCitation.document_name}
          </h3>
        </div>
        <button
          on:click={closeCitationDrawer}
          class="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
        >
          ✕ Close
        </button>
      </div>

      <div class="space-y-4 flex-1">
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div class="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
            <span class="text-slate-500 block">Page Number</span>
            <span class="text-slate-200 font-medium">{selectedCitation.page_number ?? "N/A"}</span>
          </div>
          <div class="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
            <span class="text-slate-500 block">Score</span>
            <span class="text-slate-200 font-medium">{selectedCitation.score.toFixed(4)}</span>
          </div>
        </div>

        {#if selectedCitation.section_heading}
          <div class="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs">
            <span class="text-slate-500 block mb-0.5">Section Heading</span>
            <span class="text-slate-200 font-medium">{selectedCitation.section_heading}</span>
          </div>
        {/if}

        <div class="space-y-1.5">
          <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
            Immutable Excerpt Snapshot
          </span>
          <div class="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
            {selectedCitation.excerpt}
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}

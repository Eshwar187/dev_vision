<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api/client";
  import { activeWorkspace } from "$lib/stores/workspace";
  import type { CodebaseItem, CodebaseGenerationResponse } from "$lib/api/types";

  let codebases: CodebaseItem[] = [];
  let isLoading = false;
  let actionMessage = "";
  let actionError = "";

  // Create Codebase Form State
  let showCreateModal = false;
  let newName = "";
  let newRepoUrl = "";
  let newBranch = "main";
  let isCreating = false;

  // Upload Archive State
  let showUploadModal = false;
  let uploadTargetCodebase: CodebaseItem | null = null;
  let uploadFile: File | null = null;
  let fileInput: HTMLInputElement;
  let isUploading = false;
  let indexingResult: CodebaseGenerationResponse | null = null;

  let isDeletingId: string | null = null;

  $: currentWorkspaceId = $activeWorkspace?.id;
  $: if (currentWorkspaceId) {
    loadCodebases(currentWorkspaceId);
  }

  async function loadCodebases(workspaceId: string) {
    isLoading = true;
    actionError = "";
    const res = await api.listCodebases(workspaceId);
    isLoading = false;
    if (res.success && res.data) {
      codebases = res.data.items;
    } else {
      actionError = res.error || "Failed to load codebases.";
    }
  }

  async function handleCreateCodebase() {
    if (!currentWorkspaceId || !newName.trim()) return;
    isCreating = true;
    actionError = "";
    actionMessage = "";

    const res = await api.createCodebase(currentWorkspaceId, {
      name: newName.trim(),
      repository_url: newRepoUrl.trim() || undefined,
      default_branch: newBranch.trim() || "main",
    });
    isCreating = false;

    if (res.success && res.data) {
      actionMessage = `Codebase "${res.data.name}" created successfully.`;
      showCreateModal = false;
      newName = "";
      newRepoUrl = "";
      newBranch = "main";
      await loadCodebases(currentWorkspaceId);
    } else {
      actionError = res.error || "Failed to create codebase.";
    }
  }

  function openUpload(cb: CodebaseItem) {
    uploadTargetCodebase = cb;
    uploadFile = null;
    indexingResult = null;
    showUploadModal = true;
  }

  function handleFileSelected(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      uploadFile = input.files[0];
    }
  }

  async function handleUploadArchive() {
    if (!currentWorkspaceId || !uploadTargetCodebase || !uploadFile) return;
    isUploading = true;
    actionError = "";
    actionMessage = "";
    indexingResult = null;

    const res = await api.uploadCodebaseArchive(
      currentWorkspaceId,
      uploadTargetCodebase.id,
      uploadFile
    );
    isUploading = false;

    if (res.success && res.data) {
      indexingResult = res.data;
      actionMessage = `Archive indexed! Generation #${res.data.generation_number} is now ${res.data.status}.`;
      await loadCodebases(currentWorkspaceId);
    } else {
      actionError = res.error || "Failed to index codebase archive.";
    }
  }

  async function handleDeleteCodebase(codebaseId: string) {
    if (!currentWorkspaceId) return;
    if (!confirm("Are you sure you want to delete this codebase and all indexed data?")) return;

    isDeletingId = codebaseId;
    actionError = "";
    const res = await api.deleteCodebase(currentWorkspaceId, codebaseId);
    isDeletingId = null;

    if (res.success) {
      actionMessage = "Codebase deleted successfully.";
      codebases = codebases.filter((c) => c.id !== codebaseId);
    } else {
      actionError = res.error || "Failed to delete codebase.";
    }
  }
</script>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div>
      <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full bg-cyan-500"></span>
        Codebase Intelligence
      </h1>
      <p class="text-xs text-slate-400 mt-1">
        Index software repositories, extract Tree-sitter AST symbols, and query code with deterministic citations.
      </p>
    </div>
    <div class="flex items-center gap-3">
      <button
        on:click={() => (showCreateModal = true)}
        class="inline-flex items-center gap-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-medium text-xs px-3.5 py-2 rounded-lg shadow-md shadow-cyan-600/20 transition-all"
      >
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        New Codebase
      </button>
    </div>
  </div>

  <!-- Messages -->
  {#if actionMessage}
    <div class="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-lg text-emerald-300 text-xs flex items-center justify-between">
      <span>{actionMessage}</span>
      <button on:click={() => (actionMessage = "")} class="text-emerald-400 hover:text-emerald-200">✕</button>
    </div>
  {/if}
  {#if actionError}
    <div class="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-300 text-xs flex items-center justify-between">
      <span>{actionError}</span>
      <button on:click={() => (actionError = "")} class="text-rose-400 hover:text-rose-200">✕</button>
    </div>
  {/if}

  <!-- Content List -->
  {#if isLoading}
    <div class="flex flex-col items-center justify-center p-12 bg-slate-900/40 border border-slate-800/80 rounded-xl">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-500 mb-3"></div>
      <p class="text-xs text-slate-400">Loading codebases...</p>
    </div>
  {:else if codebases.length === 0}
    <div class="flex flex-col items-center justify-center p-16 bg-slate-900/40 border border-dashed border-slate-800 rounded-xl text-center">
      <div class="h-12 w-12 rounded-full bg-slate-800/80 flex items-center justify-center text-slate-400 mb-4">
        <svg class="w-6 h-6 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      </div>
      <h3 class="text-sm font-semibold text-slate-200">No codebases indexed</h3>
      <p class="text-xs text-slate-400 max-w-sm mt-1 mb-4">
        Create a codebase and upload a ZIP archive of your source code to enable syntax-aware code intelligence.
      </p>
      <button
        on:click={() => (showCreateModal = true)}
        class="bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs px-3.5 py-2 rounded-lg border border-slate-700 transition-colors"
      >
        Create Codebase
      </button>
    </div>
  {:else}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {#each codebases as cb (cb.id)}
        <div class="bg-slate-900/60 border border-slate-800/90 hover:border-slate-700/80 rounded-xl p-5 flex flex-col justify-between transition-all group">
          <div>
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-2">
                <div class="h-7 w-7 rounded bg-slate-800 border border-slate-700 flex items-center justify-center text-cyan-400 font-mono text-xs font-bold">
                  &lt;/&gt;
                </div>
                <div>
                  <h3 class="text-sm font-semibold text-white group-hover:text-cyan-400 transition-colors">
                    <a href={`/codebases/${cb.id}`}>{cb.name}</a>
                  </h3>
                  <span class="text-[10px] text-slate-400 font-mono">branch: {cb.default_branch}</span>
                </div>
              </div>

              {#if cb.is_indexed}
                <span class="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
                  <span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  Indexed
                </span>
              {:else}
                <span class="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-400 border border-amber-800/60">
                  Not Indexed
                </span>
              {/if}
            </div>

            {#if cb.repository_url}
              <p class="text-xs text-slate-400 truncate mt-3 font-mono text-[11px]">
                {cb.repository_url}
              </p>
            {/if}
          </div>

          <div class="mt-5 pt-4 border-t border-slate-800/60 flex items-center justify-between text-xs">
            <a
              href={`/codebases/${cb.id}`}
              class="text-cyan-400 hover:text-cyan-300 font-medium inline-flex items-center gap-1 text-xs"
            >
              Explore & Query →
            </a>

            <div class="flex items-center gap-2">
              <button
                on:click={() => openUpload(cb)}
                class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors"
                title="Upload & Index Archive"
              >
                Upload ZIP
              </button>
              <button
                on:click={() => handleDeleteCodebase(cb.id)}
                disabled={isDeletingId === cb.id}
                class="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 transition-colors"
                title="Delete Codebase"
              >
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Create Modal -->
  {#if showCreateModal}
    <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 class="text-sm font-semibold text-white">Create New Codebase</h3>
          <button on:click={() => (showCreateModal = false)} class="text-slate-400 hover:text-slate-200">✕</button>
        </div>

        <div class="space-y-3">
          <div>
            <label for="codebase-name-input" class="block text-xs font-medium text-slate-300 mb-1">Codebase Name *</label>
            <input
              id="codebase-name-input"
              type="text"
              bind:value={newName}
              placeholder="e.g. Core-API or payment-service"
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label for="codebase-branch-input" class="block text-xs font-medium text-slate-300 mb-1">Default Branch</label>
            <input
              id="codebase-branch-input"
              type="text"
              bind:value={newBranch}
              placeholder="main"
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label for="codebase-repo-input" class="block text-xs font-medium text-slate-300 mb-1">Repository URL (Optional)</label>
            <input
              id="codebase-repo-input"
              type="text"
              bind:value={newRepoUrl}
              placeholder="https://github.com/org/repo"
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
          <button
            on:click={() => (showCreateModal = false)}
            class="px-3 py-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            on:click={handleCreateCodebase}
            disabled={isCreating || !newName.trim()}
            class="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-1.5 rounded-lg transition-colors"
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Upload Modal -->
  {#if showUploadModal && uploadTargetCodebase}
    <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 class="text-sm font-semibold text-white">Upload Archive — {uploadTargetCodebase.name}</h3>
          <button on:click={() => (showUploadModal = false)} class="text-slate-400 hover:text-slate-200">✕</button>
        </div>

        <div class="space-y-4">
          <p class="text-xs text-slate-400">
            Upload a <code class="text-cyan-400">.zip</code> archive of your repository. Files will be inspected for path traversal, secrets will be redacted, and symbols will be extracted using Tree-sitter.
          </p>

          <input
            type="file"
            accept=".zip"
            bind:this={fileInput}
            on:change={handleFileSelected}
            class="hidden"
          />

          <button
            type="button"
            on:click={() => fileInput.click()}
            class="w-full border-2 border-dashed border-slate-700 hover:border-cyan-500/80 rounded-xl p-6 text-center cursor-pointer transition-colors bg-slate-950/40 block"
          >
            <div class="text-slate-400 text-xs">
              {#if uploadFile}
                <span class="text-white font-medium">{uploadFile.name}</span>
                <span class="text-slate-500 block text-[11px] mt-1">({(uploadFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              {:else}
                <span>Click to select repository <strong class="text-cyan-400">.zip</strong> archive</span>
              {/if}
            </div>
          </button>

          {#if indexingResult}
            <div class="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1.5 text-xs font-mono">
              <div class="text-emerald-400 font-semibold">Indexing Complete: Generation #{indexingResult.generation_number}</div>
              <div class="text-slate-400 text-[11px]">Status: <span class="text-white">{indexingResult.status}</span></div>
              <div class="text-slate-400 text-[11px]">Files: <span class="text-white">{indexingResult.total_files}</span> | Symbols: <span class="text-white">{indexingResult.total_symbols}</span> | Chunks: <span class="text-white">{indexingResult.total_chunks}</span></div>
            </div>
          {/if}
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
          <button
            on:click={() => (showUploadModal = false)}
            class="px-3 py-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            Close
          </button>
          <button
            on:click={handleUploadArchive}
            disabled={isUploading || !uploadFile}
            class="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-1.5 rounded-lg transition-colors flex items-center gap-2"
          >
            {#if isUploading}
              <div class="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></div>
              Indexing Archive...
            {:else}
              Start Indexing
            {/if}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<script lang="ts">
  import { api } from "$lib/api/client";
  import { setUser } from "$lib/stores/auth";
  import { goto } from "$app/navigation";

  let email = "";
  let password = "";
  let errorMessage = "";
  let isSubmitting = false;

  async function handleLogin() {
    errorMessage = "";
    if (!email || !password) {
      errorMessage = "Please enter your email and password.";
      return;
    }

    isSubmitting = true;
    const result = await api.login(email, password);
    isSubmitting = false;

    if (result.success && result.data?.user) {
      setUser(result.data.user);
      goto("/app");
    } else {
      errorMessage = result.error || "Invalid email or password.";
    }
  }
</script>

<div class="space-y-6">
  <div>
    <h3 class="text-lg font-semibold text-white">Sign In</h3>
    <p class="text-xs text-slate-400 mt-1">Access your workspaces and developer copilot.</p>
  </div>

  {#if errorMessage}
    <div class="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs">
      {errorMessage}
    </div>
  {/if}

  <form on:submit|preventDefault={handleLogin} class="space-y-4">
    <div class="space-y-1">
      <label for="email" class="text-xs font-medium text-slate-300">Email Address</label>
      <input
        id="email"
        type="email"
        bind:value={email}
        placeholder="developer@example.com"
        required
        class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 transition-colors"
      />
    </div>

    <div class="space-y-1">
      <label for="password" class="text-xs font-medium text-slate-300">Password</label>
      <input
        id="password"
        type="password"
        bind:value={password}
        placeholder="••••••••••••"
        required
        class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 transition-colors"
      />
    </div>

    <button
      type="submit"
      disabled={isSubmitting}
      class="w-full py-2.5 px-4 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-sm transition-all shadow-md shadow-cyan-600/20 active:scale-[0.99] flex items-center justify-center gap-2"
    >
      {#if isSubmitting}
        <span class="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
        Signing in...
      {:else}
        Sign In
      {/if}
    </button>
  </form>

  <div class="text-center text-xs text-slate-400">
    Don't have an account?
    <a href="/register" class="text-cyan-400 hover:text-cyan-300 font-medium">Create one</a>
  </div>
</div>
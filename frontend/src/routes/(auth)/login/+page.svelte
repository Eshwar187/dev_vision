<script lang="ts">
  import { api } from "$lib/api/client";
  import { setUser } from "$lib/stores/auth";
  import { goto } from "$app/navigation";
  import { Lock, Mail, ArrowRight, Shield, Terminal, AlertCircle } from "lucide-svelte";

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
  <div class="space-y-1">
    <div class="flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 uppercase tracking-wider mb-2">
      <Lock class="w-3 h-3" />
      <span>Secure Tenant Sign-In</span>
    </div>
    <h2 class="text-xl font-bold text-white tracking-tight">Access Your Console</h2>
    <p class="text-xs text-slate-400">Authenticate with opaque session credentials.</p>
  </div>

  {#if errorMessage}
    <div class="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      <span>{errorMessage}</span>
    </div>
  {/if}

  <form on:submit|preventDefault={handleLogin} class="space-y-4 text-xs">
    <div class="space-y-1.5">
      <label for="login-email" class="block font-medium text-slate-300">Work Email Address</label>
      <div class="relative">
        <input
          id="login-email"
          type="email"
          bind:value={email}
          placeholder="developer@company.com"
          required
          class="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors text-xs"
        />
        <Mail class="w-4 h-4 text-slate-500 absolute left-3 top-3 pointer-events-none" />
      </div>
    </div>

    <div class="space-y-1.5">
      <div class="flex items-center justify-between">
        <label for="login-password" class="block font-medium text-slate-300">Account Password</label>
        <span class="text-[10px] text-slate-500 font-mono">Argon2id Hash</span>
      </div>
      <div class="relative">
        <input
          id="login-password"
          type="password"
          bind:value={password}
          placeholder="••••••••••••"
          required
          class="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors text-xs"
        />
        <Lock class="w-4 h-4 text-slate-500 absolute left-3 top-3 pointer-events-none" />
      </div>
    </div>

    <button
      type="submit"
      disabled={isSubmitting}
      class="w-full py-2.5 px-4 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-xs transition-all shadow-md shadow-cyan-600/20 active:scale-[0.99] flex items-center justify-center gap-2 mt-2"
    >
      {#if isSubmitting}
        <span class="h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
        <span>Authenticating...</span>
      {:else}
        <span>Sign In to Workspace</span>
        <ArrowRight class="w-3.5 h-3.5" />
      {/if}
    </button>
  </form>

  <div class="pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
    Need a new workspace?
    <a href="/register" class="text-cyan-400 hover:text-cyan-300 font-medium ml-1">Create an account</a>
  </div>
</div>
<script lang="ts">
  import { api } from "$lib/api/client";
  import { setUser } from "$lib/stores/auth";
  import { goto } from "$app/navigation";
  import { User, Mail, Lock, ArrowRight, ShieldCheck, AlertCircle, CheckCircle2 } from "lucide-svelte";

  let displayName = "";
  let email = "";
  let password = "";
  let confirmPassword = "";
  let errorMessage = "";
  let infoMessage = "";
  let isSubmitting = false;

  async function handleRegister() {
    errorMessage = "";
    infoMessage = "";

    if (!displayName || !email || !password) {
      errorMessage = "All fields are required.";
      return;
    }

    if (password.length < 12) {
      errorMessage = "Password must be at least 12 characters.";
      return;
    }

    if (password !== confirmPassword) {
      errorMessage = "Passwords do not match.";
      return;
    }

    isSubmitting = true;
    const result = await api.register(email, password, displayName);
    isSubmitting = false;

    if (result.success && result.data) {
      if (result.data.user) {
        setUser(result.data.user);
        goto("/app");
      } else {
        infoMessage = result.data.message || "Account registered successfully. Please sign in.";
      }
    } else {
      errorMessage = result.error || "Registration failed. Please try again.";
    }
  }
</script>

<div class="space-y-6">
  <div class="space-y-1">
    <div class="flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 uppercase tracking-wider mb-2">
      <ShieldCheck class="w-3 h-3" />
      <span>New Workspace Account</span>
    </div>
    <h2 class="text-xl font-bold text-white tracking-tight">Create Your Account</h2>
    <p class="text-xs text-slate-400">Initialize an isolated personal developer workspace.</p>
  </div>

  {#if errorMessage}
    <div class="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      <span>{errorMessage}</span>
    </div>
  {/if}

  {#if infoMessage}
    <div class="p-3.5 rounded-lg bg-cyan-950/80 border border-cyan-800 text-cyan-300 text-xs space-y-2">
      <div class="flex items-center gap-2 font-medium">
        <CheckCircle2 class="w-4 h-4 text-cyan-400" />
        <span>{infoMessage}</span>
      </div>
      <a href="/login" class="inline-block text-white font-semibold underline text-xs">
        Proceed to Sign In &rarr;
      </a>
    </div>
  {/if}

  <form on:submit|preventDefault={handleRegister} class="space-y-3.5 text-xs">
    <div class="space-y-1.5">
      <label for="reg-name" class="block font-medium text-slate-300">Display Name</label>
      <div class="relative">
        <input
          id="reg-name"
          type="text"
          bind:value={displayName}
          placeholder="Jane Developer"
          required
          class="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors text-xs"
        />
        <User class="w-4 h-4 text-slate-500 absolute left-3 top-3 pointer-events-none" />
      </div>
    </div>

    <div class="space-y-1.5">
      <label for="reg-email" class="block font-medium text-slate-300">Work Email Address</label>
      <div class="relative">
        <input
          id="reg-email"
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
        <label for="reg-password" class="block font-medium text-slate-300">Password</label>
        <span class="text-[10px] text-slate-500 font-mono">Min 12 characters</span>
      </div>
      <div class="relative">
        <input
          id="reg-password"
          type="password"
          bind:value={password}
          placeholder="••••••••••••"
          required
          class="w-full pl-9 pr-3 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors text-xs"
        />
        <Lock class="w-4 h-4 text-slate-500 absolute left-3 top-3 pointer-events-none" />
      </div>
    </div>

    <div class="space-y-1.5">
      <label for="reg-confirm" class="block font-medium text-slate-300">Confirm Password</label>
      <div class="relative">
        <input
          id="reg-confirm"
          type="password"
          bind:value={confirmPassword}
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
        <span>Creating Account...</span>
      {:else}
        <span>Initialize Workspace Account</span>
        <ArrowRight class="w-3.5 h-3.5" />
      {/if}
    </button>
  </form>

  <div class="pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
    Already registered?
    <a href="/login" class="text-cyan-400 hover:text-cyan-300 font-medium ml-1">Sign in here</a>
  </div>
</div>
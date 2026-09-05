<script lang="ts">
  import { api } from "$lib/api/client";
  import { setUser } from "$lib/stores/auth";
  import { goto } from "$app/navigation";

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
        // Anti-enumeration notification
        infoMessage = result.data.message || "Registration received. Please log in.";
      }
    } else {
      errorMessage = result.error || "Registration failed. Please try again.";
    }
  }
</script>

<div class="space-y-6">
  <div>
    <h3 class="text-lg font-semibold text-white">Create Account</h3>
    <p class="text-xs text-slate-400 mt-1">Get started with an isolated personal workspace.</p>
  </div>

  {#if errorMessage}
    <div class="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs">
      {errorMessage}
    </div>
  {/if}

  {#if infoMessage}
    <div class="p-3 rounded-lg bg-cyan-950/80 border border-cyan-800 text-cyan-300 text-xs space-y-2">
      <p>{infoMessage}</p>
      <a href="/login" class="inline-block font-semibold underline">Proceed to Sign In &rarr;</a>
    </div>
  {/if}

  <form on:submit|preventDefault={handleRegister} class="space-y-4">
    <div class="space-y-1">
      <label for="displayName" class="text-xs font-medium text-slate-300">Display Name</label>
      <input
        id="displayName"
        type="text"
        bind:value={displayName}
        placeholder="Jane Developer"
        required
        class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 transition-colors"
      />
    </div>

    <div class="space-y-1">
      <label for="regEmail" class="text-xs font-medium text-slate-300">Email Address</label>
      <input
        id="regEmail"
        type="email"
        bind:value={email}
        placeholder="developer@example.com"
        required
        class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 transition-colors"
      />
    </div>

    <div class="space-y-1">
      <div class="flex items-center justify-between">
        <label for="regPassword" class="text-xs font-medium text-slate-300">Password</label>
        <span class="text-[11px] text-slate-500">Min 12 characters</span>
      </div>
      <input
        id="regPassword"
        type="password"
        bind:value={password}
        placeholder="Minimum 12 characters"
        required
        minlength="12"
        class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 transition-colors"
      />
    </div>

    <div class="space-y-1">
      <label for="confirmPassword" class="text-xs font-medium text-slate-300">Confirm Password</label>
      <input
        id="confirmPassword"
        type="password"
        bind:value={confirmPassword}
        placeholder="Re-enter password"
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
        Creating account...
      {:else}
        Create Account
      {/if}
    </button>
  </form>

  <div class="text-center text-xs text-slate-400">
    Already have an account?
    <a href="/login" class="text-cyan-400 hover:text-cyan-300 font-medium">Sign in</a>
  </div>
</div>
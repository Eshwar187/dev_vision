import { writable, derived } from "svelte/store";
import type { User } from "$lib/api/types";
import { api } from "$lib/api/client";

export const currentUser = writable<User | null>(null);
export const isAuthLoading = writable<boolean>(true);
export const isAuthenticated = derived(currentUser, ($u) => $u !== null);

export function setUser(user: User | null): void {
  currentUser.set(user);
  isAuthLoading.set(false);
}

export function clearUser(): void {
  currentUser.set(null);
  isAuthLoading.set(false);
}

export async function refreshCurrentUser(): Promise<User | null> {
  isAuthLoading.set(true);
  const result = await api.getMe();
  if (result.success && result.data?.user) {
    setUser(result.data.user);
    return result.data.user;
  } else {
    clearUser();
    return null;
  }
}
import { writable } from "svelte/store";
import type { Workspace } from "$lib/api/types";
import { api } from "$lib/api/client";

export const workspaces = writable<Workspace[]>([]);
export const activeWorkspace = writable<Workspace | null>(null);
export const isWorkspacesLoading = writable<boolean>(false);

export function setWorkspaces(list: Workspace[]): void {
  workspaces.set(list);
  if (list.length > 0) {
    activeWorkspace.update((current) => {
      if (!current || !list.some((w) => w.id === current.id)) {
        return list[0];
      }
      return current;
    });
  } else {
    activeWorkspace.set(null);
  }
}

export function setActiveWorkspace(ws: Workspace | null): void {
  activeWorkspace.set(ws);
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  isWorkspacesLoading.set(true);
  const result = await api.listWorkspaces();
  isWorkspacesLoading.set(false);
  if (result.success && result.data) {
    setWorkspaces(result.data);
    return result.data;
  }
  return [];
}
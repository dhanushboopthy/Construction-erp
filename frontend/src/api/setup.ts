import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  Location,
  LocationCreate,
  LocationUpdate,
  ShopSettings,
  ShopSettingsUpdate,
  User,
  UserCreate,
  UserUpdate,
} from "./types";

/** Milestone 1 setup data: shop settings, users and locations (owner screens). */

const keys = {
  settings: ["settings"] as const,
  users: ["users"] as const,
  locations: (all: boolean) => ["locations", { all }] as const,
};

export function useShopSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: () => api<ShopSettings>("/settings") });
}

export function useSaveShopSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ShopSettingsUpdate) =>
      api<ShopSettings>("/settings", { method: "PUT", body: json(body) }),
    onSuccess: (data) => client.setQueryData(keys.settings, data),
  });
}

export function useUsers() {
  return useQuery({ queryKey: keys.users, queryFn: () => api<User[]>("/users") });
}

export function useCreateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreate) => api<User>("/users", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UserUpdate }) =>
      api<User>(`/users/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      api<undefined>(`/users/${id}/reset-password`, {
        method: "POST",
        body: json({ new_password: password }),
      }),
  });
}

export function useLocations(includeInactive = false) {
  return useQuery({
    queryKey: keys.locations(includeInactive),
    queryFn: () => api<Location[]>(`/locations${includeInactive ? "?include_inactive=true" : ""}`),
  });
}

function useLocationInvalidation() {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: ["locations"] });
    await client.invalidateQueries({ queryKey: keys.users }); // users embed their locations
  };
}

export function useCreateLocation() {
  const invalidate = useLocationInvalidation();
  return useMutation({
    mutationFn: (body: LocationCreate) =>
      api<Location>("/locations", { method: "POST", body: json(body) }),
    onSuccess: invalidate,
  });
}

export function useUpdateLocation() {
  const invalidate = useLocationInvalidation();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: LocationUpdate }) =>
      api<Location>(`/locations/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: invalidate,
  });
}

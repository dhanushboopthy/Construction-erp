import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, json } from "./client";
import type {
  DropShipLinkCreate,
  DropShipReport,
  OpenDirectLine,
  Page,
  Trip,
  TripCreate,
  Vehicle,
  VehicleCreate,
} from "./types";

/** Milestone 9: vehicles, trips, freight and direct (drop-ship) sales. */

export function useVehicles(includeInactive = false) {
  return useQuery({
    queryKey: ["vehicles", includeInactive],
    queryFn: () => api<Vehicle[]>(`/vehicles?include_inactive=${includeInactive}`),
  });
}

export function useCreateVehicle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: VehicleCreate) =>
      api<Vehicle>("/vehicles", { method: "POST", body: json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["vehicles"] }),
  });
}

export function useToggleVehicle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      api<Vehicle>(`/vehicles/${id}`, { method: "PATCH", body: json({ is_active }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["vehicles"] }),
  });
}

export function useTrips() {
  return useQuery({
    queryKey: ["trips"],
    queryFn: () => api<Page<Trip>>("/trips?limit=100"),
  });
}

export function useCreateTrip() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TripCreate) => api<Trip>("/trips", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of ["trips", "statement", "dues", "invoice", "drop-ship"]) {
        await client.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useOpenDirectLines(itemId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["drop-ship", "open", itemId],
    enabled: enabled && itemId !== null,
    queryFn: () => api<OpenDirectLine[]>(`/drop-ship/open-purchases?item_id=${itemId}`),
  });
}

export function useLinkDropShip() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DropShipLinkCreate) =>
      api<unknown>("/drop-ship/links", { method: "POST", body: json(body) }),
    onSuccess: async () => {
      for (const key of ["invoice", "drop-ship"]) {
        await client.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useDropShipReport() {
  return useQuery({
    queryKey: ["drop-ship", "report"],
    queryFn: () => api<DropShipReport>("/reports/drop-ship"),
  });
}

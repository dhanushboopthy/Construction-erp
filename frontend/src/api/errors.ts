import { ApiError } from "./client";

export interface FormError {
  field: string | null;
  message: string;
}

/** Turn any failure into one message, tied to a form field when the API names one. */
export function toFormError(error: unknown): FormError {
  if (error instanceof ApiError) {
    return { field: error.body.field ?? null, message: error.message };
  }
  return { field: null, message: "Cannot reach the server. Check the network and try again." };
}

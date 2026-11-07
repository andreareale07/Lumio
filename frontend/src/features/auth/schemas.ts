import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().min(1, "Inserisci la tua email").email("Email non valida"),
  password: z.string().min(1, "Inserisci la password"),
  // Solo con la 2FA attiva: il campo compare quando il server lo chiede.
  totpCode: z.string().optional(),
});
export type LoginFormValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  displayName: z.string().min(1, "Inserisci il tuo nome"),
  email: z.string().min(1, "Inserisci la tua email").email("Email non valida"),
  password: z.string().min(8, "Almeno 8 caratteri"),
});
export type RegisterFormValues = z.infer<typeof registerSchema>;

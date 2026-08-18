import { z } from 'zod';

export const loginSchema = z.object({
  username: z.string().min(1, 'Ingresa tu usuario de red'),
  password: z.string().min(1, 'Ingresa tu contraseña'),
  remember: z.boolean(),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

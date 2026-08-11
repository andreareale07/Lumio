import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../app/providers/AuthProvider";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { type RegisterFormValues, registerSchema } from "./schemas";

export function RegisterPage() {
  const { register: registerUser } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = async (values: RegisterFormValues) => {
    setFormError(null);
    try {
      await registerUser(values.email, values.password, values.displayName);
      navigate("/accounts", { replace: true });
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Non è stato possibile completare la registrazione."));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-sm">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-text">Lumio</h1>
          <p className="text-sm text-text-muted">Crea il tuo account</p>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          <Input
            label="Nome"
            autoComplete="name"
            error={errors.displayName?.message}
            {...register("displayName")}
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            hint="Almeno 8 caratteri"
            error={errors.password?.message}
            {...register("password")}
          />
          {formError && (
            <p role="alert" className="text-sm text-danger">
              {formError}
            </p>
          )}
          <Button type="submit" loading={isSubmitting} className="w-full">
            Crea account
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-text-muted">
          Hai già un account?{" "}
          <Link to="/login" className="font-medium text-primary">
            Accedi
          </Link>
        </p>
      </div>
    </div>
  );
}

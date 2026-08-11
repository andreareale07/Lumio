import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../app/providers/AuthProvider";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { type LoginFormValues, loginSchema } from "./schemas";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      const redirectTo = (location.state as { from?: string } | null)?.from ?? "/accounts";
      navigate(redirectTo, { replace: true });
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Email o password non corrette."));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-sm">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-text">Lumio</h1>
          <p className="text-sm text-text-muted">See your money clearly.</p>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
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
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />
          {formError && (
            <p role="alert" className="text-sm text-danger">
              {formError}
            </p>
          )}
          <Button type="submit" loading={isSubmitting} className="w-full">
            Accedi
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-text-muted">
          Non hai un account?{" "}
          <Link to="/register" className="font-medium text-primary">
            Registrati
          </Link>
        </p>
      </div>
    </div>
  );
}

"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, TextField } from "@/components/app/bits";
import { isAdminRole, useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";
import { t } from "@/i18n";

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  useEffect(() => {
    if (user) router.replace(isAdminRole(user.role) || user.role === "auditor" ? "/admin" : "/");
  }, [user, router]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">{t("app.name")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("login.title")}</p>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={(e) => {
            e.preventDefault();
            void run(() => login(email, password));
          }}>
            <TextField label={t("common.email")} name="email" type="email" value={email} onChange={setEmail} required />
            <TextField label={t("common.password")} name="password" type="password" value={password} onChange={setPassword} required />
            <ErrorText>{error}</ErrorText>
            <Button type="submit" disabled={busy} data-testid="login-submit">{t("login.submit")}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

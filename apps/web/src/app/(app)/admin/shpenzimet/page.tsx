import { Suspense } from "react";
import { ExpenseList } from "@/components/app/expense-list";

export default function Page() {
  return <Suspense><ExpenseList admin /></Suspense>;
}

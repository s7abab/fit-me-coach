import { auth } from "@/auth";
import App from "@/components/App";
import SignIn from "@/components/SignIn";

export default async function Page({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return <SignIn failed={Boolean((await searchParams).error)} />;
  return <App />;
}

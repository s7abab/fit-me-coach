import { signInWithGoogle } from "@/app/actions";

export default function SignIn({ failed }: { failed: boolean }) {
  return (
    <main className="signin">
      <span className="wordmark">fit me<i /></span>
      <h1>A coach that reads your own sleep, recovery and training</h1>
      <p>
        Sign in with Google and share your Google Health data. Fit Me Coach only reads it: steps, workouts,
        sleep, resting heart rate and HRV.
      </p>
      <form action={signInWithGoogle}>
        <button type="submit" className="button">Continue with Google</button>
      </form>
      {failed && <p className="answer-error" role="alert">Sign-in did not finish. Please try again.</p>}
      <p className="fine">Cites published guidelines. Not medical advice.</p>
    </main>
  );
}

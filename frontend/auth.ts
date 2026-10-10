import NextAuth, { type DefaultSession } from "next-auth";
import Google from "next-auth/providers/google";
import { backendFetch } from "@/lib/backend";

declare module "next-auth" {
  interface Session {
    user: { id: string } & DefaultSession["user"];
  }
}

// Read-only access to the Google Health data the coach uses
const HEALTH_SCOPES = [
  "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly", // steps, workouts
  "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
  "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly", // resting HR, HRV
];

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      authorization: {
        params: {
          scope: ["openid", "email", "profile", ...HEALTH_SCOPES].join(" "),
          // Google only hands out a refresh token when asked for offline access with a consent screen
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/", error: "/" },
  callbacks: {
    signIn({ profile }) {
      return profile?.email_verified === true;
    },
    async jwt({ token, account, profile }) {
      // `account` is only present right after Google sends the user back
      if (account && profile?.email) {
        token.googleSub = account.providerAccountId;
        token.email = profile.email;
        if (account.refresh_token) {
          // The refresh token goes straight to the backend, which stores it encrypted.
          // It is never put in the session cookie.
          const user = { id: account.providerAccountId, email: profile.email, name: profile.name };
          try {
            const res = await backendFetch(user, "/connections/google-health", {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ refresh_token: account.refresh_token, scope: account.scope ?? "" }),
            });
            if (!res.ok) console.error(`Could not save the Google Health connection (${res.status})`);
          } catch {
            // Sign-in still works; the app will show "Connect Google Health"
            console.error("Could not reach the backend to save the Google Health connection");
          }
        }
      }
      return token;
    },
    session({ session, token }) {
      if (typeof token.googleSub === "string") session.user.id = token.googleSub;
      return session;
    },
  },
});

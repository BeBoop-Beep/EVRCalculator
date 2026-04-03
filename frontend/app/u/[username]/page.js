import { redirect } from "next/navigation";

export default async function PublicProfileIndexPage({ params }) {
  const { username } = await params;
  const normalizedUsername = (username || "").trim();

  if (!normalizedUsername) {
    redirect("/");
  }

  redirect(`/u/${encodeURIComponent(normalizedUsername)}/collection`);
}

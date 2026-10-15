import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRegistries } from "./api/hooks";

const KEY = "owl.registry";

function stored(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The registry the user is looking at: URL first, then the last one used, then the first available. */
export function useCurrentRegistry(): { slug: string | null; isLoading: boolean } {
  const params = useParams();
  const registries = useRegistries();
  const list = registries.data ?? [];
  const fromUrl = params.registry ?? null;
  const remembered = stored();
  const slug =
    fromUrl ??
    (remembered && list.some((r) => r.slug === remembered) ? remembered : null) ??
    list.find((r) => r.slug === "default")?.slug ??
    list[0]?.slug ??
    null;
  useEffect(() => {
    if (slug) {
      try {
        window.localStorage.setItem(KEY, slug);
      } catch {
        /* ignore */
      }
    }
  }, [slug]);
  return { slug, isLoading: registries.isLoading };
}

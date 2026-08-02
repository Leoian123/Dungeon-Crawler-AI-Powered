// Il thread play-by-post: accumulo di POST (testo), mai di stato — lo snapshot
// vive a parte e si sostituisce in blocco (C-4). Autoscroll sull'ultimo post.

import { useEffect, useRef } from "react";
import type { PostThread } from "../api/tipi";
import { PostEvento, PostGM } from "./PostGM";

export function ThreadForum({ post }: { post: PostThread[] }) {
  const fondo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fondo.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [post.length]);

  return (
    <div className="flex flex-col gap-4">
      {post.length === 0 && (
        <p className="text-center italic text-pergamena/50">
          Il dungeon attende il primo turno del GM…
        </p>
      )}
      {post.map((p) =>
        p.genere === "gm" && p.messaggio ? (
          <PostGM key={p.id} id={p.id} messaggio={p.messaggio} />
        ) : (
          <PostEvento key={p.id} righe={p.righe} />
        ),
      )}
      <div ref={fondo} />
    </div>
  );
}

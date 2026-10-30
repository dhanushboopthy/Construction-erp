import { useRef, useState } from "react";

import { toFormError } from "@/api/errors";
import { useRemoveLogo, useTenant, useUploadLogo } from "@/api/tenant";
import { BrandMark } from "@/components/BrandMark";
import { Button } from "@/components/Button";

import ledger from "@/components/Ledger.module.css";
import styles from "./LogoSection.module.css";

export const MAX_LOGO_BYTES = 200 * 1024;

// Strings in one place so Tamil labels can be added later (docs/DESIGN.md, principle 7).
const T = {
  title: "Shop logo",
  note: "Shown in the sidebar and on the sign-in page. Without one, the shop's initials are shown.",
  choose: "Choose logo",
  replace: "Replace logo",
  remove: "Remove logo",
  hint: "A square PNG or plain SVG, up to 200 KB.",
  tooBig: "The logo is larger than 200 KB. Use a smaller file.",
  saved: "Logo saved.",
  removed: "Logo removed.",
};

/** Owner only (the page is). Uploads act at once; they are not part of "Save shop details". */
export function LogoSection() {
  const tenant = useTenant();
  const upload = useUploadLogo();
  const remove = useRemoveLogo();
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const logo = tenant.data?.logo_url ?? null;
  const busy = upload.isPending || remove.isPending;

  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setMessage({ text: T.tooBig, error: true });
    } else {
      upload.mutate(file, {
        onSuccess: () => setMessage({ text: T.saved, error: false }),
        onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
      });
    }
    if (input.current) input.current.value = ""; // so choosing the same file again still fires
  };

  return (
    <section className={ledger.group} aria-labelledby="logo-title">
      <div className={ledger.groupHead}>
        <h2 id="logo-title">{T.title}</h2>
        <p>{T.note}</p>
      </div>
      <div>
        <div className={styles.row}>
          <BrandMark name={tenant.data?.name} logoUrl={logo} className={styles.preview} />
          <div className={styles.actions}>
            <input
              ref={input}
              id="logo-file"
              type="file"
              accept="image/png,image/svg+xml"
              className={styles.file}
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
            <Button disabled={busy} onClick={() => input.current?.click()}>
              {logo ? T.replace : T.choose}
            </Button>
            {logo ? (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  remove.mutate(undefined, {
                    onSuccess: () => setMessage({ text: T.removed, error: false }),
                    onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
                  })
                }
              >
                {T.remove}
              </Button>
            ) : null}
          </div>
        </div>
        <p className={styles.hint}>{T.hint}</p>
        {message ? (
          <p
            className={message.error ? styles.error : styles.hint}
            role={message.error ? "alert" : "status"}
          >
            {message.text}
          </p>
        ) : null}
      </div>
    </section>
  );
}

import { act, fireEvent, render, screen } from "@testing-library/react";

import { InstallButton } from "./InstallButton";
import { startInstallCapture } from "./install";

/** What Chrome sends when the page can be installed. */
function offer(outcome: "accepted" | "dismissed" = "accepted") {
  const event = new Event("beforeinstallprompt", { cancelable: true });
  const prompt = vi.fn(async () => undefined);
  Object.assign(event, { prompt, userChoice: Promise.resolve({ outcome }) });
  return { event, prompt };
}

const button = () => screen.queryByRole("button", { name: /install app/i });
const clickInstall = () => fireEvent.click(screen.getByRole("button", { name: /install app/i }));

describe("InstallButton", () => {
  // The capture listens on the window for the whole test file, as it does in the app.
  beforeAll(() => startInstallCapture());
  afterEach(() => vi.unstubAllGlobals());

  it("is always there, and says how to install when the browser has made no offer", () => {
    render(<InstallButton />);
    clickInstall();
    expect(screen.getByRole("dialog", { name: "How to install" })).toHaveTextContent(
      /Add to Home screen/,
    );
  });

  it("opens the browser's dialog when it has offered, then hides once accepted", async () => {
    render(<InstallButton />);
    const { event, prompt } = offer();
    act(() => {
      window.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(true);
    clickInstall();
    await act(async () => undefined);
    expect(prompt).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog", { name: "How to install" })).toBeNull();
    expect(button()).toBeNull();
  });

  it("stays when the person dismisses the browser's dialog", async () => {
    render(<InstallButton />);
    act(() => {
      window.dispatchEvent(offer("dismissed").event);
    });
    clickInstall();
    await act(async () => undefined);
    expect(button()).not.toBeNull();
  });

  it("is hidden inside the installed app", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<InstallButton />);
    expect(button()).toBeNull();
  });
});

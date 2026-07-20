describe("Root redirect", () => {
  it("root page module imports without error", async () => {
    // Root page.tsx redirects — just ensure it can be imported without throwing.
    await expect(import("@/app/page")).resolves.toBeDefined();
  });
});

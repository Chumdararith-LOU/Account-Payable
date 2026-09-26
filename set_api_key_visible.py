"""
set_api_key_visible.py

Plain visible-input version (not hidden) so you can see exactly what
was pasted before it's saved. Seeing it in your own terminal is fine —
it's only a problem if it's ever pasted into a chat or screenshotted.

Run with:
    python set_api_key_visible.py
"""

key = input("Paste your Anthropic API key here, then press Enter: ").strip()

with open(".env", "w") as f:
    f.write(f"ANTHROPIC_API_KEY={key}\n")

print(f"\nSaved to .env.")
print(f"Length: {len(key)} characters")
print(f"Starts with: {key[:15]}")
print(f"Ends with: {key[-6:]}")

if len(key) < 50:
    print("\n⚠️  Too short for a real key — the paste likely didn't work.")
else:
    print("\n✅ Length looks right for a real key.")
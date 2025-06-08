import json
import os

# Generate 64 random bytes
keypair = [int(b) for b in os.urandom(64)]

# Save to file
with open('devnet-keypair.json', 'w') as f:
    json.dump(keypair, f)

print("Keypair generated!")
print(f"Length: {len(keypair)} bytes")

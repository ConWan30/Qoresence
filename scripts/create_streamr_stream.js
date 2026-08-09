// Create a Streamr stream and grant a local Streamr node permission to publish.
//
// Usage:
//   node scripts/create_streamr_stream.js <private-key> <broker-node-address> <stream-path>
//
// Example:
//   node scripts/create_streamr_stream.js 0xYourPrivateKey 0xYourNodeAddress qoresence/football
//
// The stream id will be 0x<private-key-address>/qoresence/football.
//
// The script defaults to Polygon Amoy testnet (no real POL required). For
// Polygon mainnet, change the `polygonAmoy: true` line below.

const { StreamrClient, StreamPermission } = require("@streamr/sdk");

async function main() {
  const [privateKey, brokerNodeAddress, streamPath] = process.argv.slice(2);

  if (!privateKey || !brokerNodeAddress || !streamPath) {
    console.error(
      "Usage: node scripts/create_streamr_stream.js <private-key> <broker-node-address> <stream-path>"
    );
    console.error(
      "Example: node scripts/create_streamr_stream.js 0xabc... 0xnode... qoresence/football"
    );
    process.exit(1);
  }

  const streamr = new StreamrClient({
    auth: { privateKey },
    // Use Polygon Amoy testnet by default. Set to false for mainnet.
    polygonAmoy: process.env.USE_STREAMR_MAINNET !== "1",
  });

  try {
    const stream = await streamr.getOrCreateStream({ id: `/${streamPath}` });
    console.log("Stream ID:", stream.id);

    await stream.grantPermissions({
      userId: brokerNodeAddress,
      permissions: [StreamPermission.PUBLISH, StreamPermission.SUBSCRIBE],
    });
    console.log("Granted PUBLISH + SUBSCRIBE to", brokerNodeAddress);

    // Optionally grant public subscribe so anyone can listen without a key.
    if (process.env.STREAMR_PUBLIC_SUBSCRIBE === "1") {
      await stream.grantPermissions({
        userId: "0x0000000000000000000000000000000000000000",
        permissions: [StreamPermission.SUBSCRIBE],
      });
      console.log("Granted public SUBSCRIBE");
    }
  } catch (e) {
    console.error("Failed to create stream or set permissions:", e.message);
    process.exit(1);
  } finally {
    await streamr.destroy();
  }
}

main();

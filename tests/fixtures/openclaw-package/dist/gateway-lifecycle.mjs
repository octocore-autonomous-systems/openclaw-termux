// Synthetic stand-in for OpenClaw's gateway restart lifecycle (test fixture).
const WINDOWS_POST_RESTART_HEALTH_TIMEOUT_MS = 18e4;
const DEFAULT_RESTART_HEALTH_ATTEMPTS = 60;
function resolveGatewayService() {
	return { isLoaded: async () => true };
}
function restartHealthAttempts() {
	return process.platform === "win32" ? Math.ceil(WINDOWS_POST_RESTART_HEALTH_TIMEOUT_MS / 500) : DEFAULT_RESTART_HEALTH_ATTEMPTS;
}
async function restartOwnedProcess(owner) {
	const service = resolveGatewayService();
	if (!owner || owner.state === "dead" || owner.mode !== "foreground") return null;
	return service;
}
export { restartHealthAttempts, restartOwnedProcess };

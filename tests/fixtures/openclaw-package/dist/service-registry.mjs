// Synthetic stand-in for OpenClaw's gateway service registry (test fixture, not OpenClaw code).
import fs from "node:fs";
//#region src/daemon/service.ts
function ignoreServiceWriteResult(fn) {
	return async (args) => {
		await fn(args);
	};
}
const GATEWAY_SERVICE_REGISTRY = {
	darwin: {
		label: "launchd"
	},
	linux: {
		label: "systemd"
	},
	win32: {
		label: "Scheduled Task"
	}
};
function resolveGatewayService() {
	return GATEWAY_SERVICE_REGISTRY[process.platform] ?? null;
}
//#endregion
export { GATEWAY_SERVICE_REGISTRY, fs, ignoreServiceWriteResult, resolveGatewayService };

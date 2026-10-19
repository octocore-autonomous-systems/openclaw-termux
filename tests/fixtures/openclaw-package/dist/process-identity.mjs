// Synthetic stand-in for OpenClaw's /proc process identity (test fixture).
function isValidPid(pid) {
	return Number.isInteger(pid) && pid > 0;
}
function getProcessStartTime(pid) {
	if (!isValidPid(pid) || process.platform !== "linux") return null;
	return 0;
}
export { getProcessStartTime };

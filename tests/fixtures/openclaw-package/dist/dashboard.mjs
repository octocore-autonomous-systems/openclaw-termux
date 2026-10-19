// Synthetic stand-in for OpenClaw's dashboard command (test fixture).
async function dashboardCommand(options = {}) {
	if (!options.noOpen) {
		console.log("opening the dashboard in a browser");
	}
}
export { dashboardCommand };

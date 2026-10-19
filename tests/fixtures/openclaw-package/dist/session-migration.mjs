// Synthetic stand-in for OpenClaw's session-SQLite migration archive move (test fixture).
import fs from "node:fs";
import path from "node:path";
function sameMigrationArtifact(a, b) {
	return JSON.stringify(a) === JSON.stringify(b);
}
function readMigrationArtifactIdentity(file) {
	const stat = fs.statSync(file);
	return { size: stat.size };
}
function requireDirectorySync(ok, label) {
	if (!ok) throw new Error(label);
}
async function syncDirectory(dir) {
	return Boolean(dir);
}
async function moveMigrationArtifact(sourcePath, targetPath, expected, onPublished, publishSourceRemoval) {
	let createdPublication = false;
	fs.linkSync(sourcePath, targetPath);
	createdPublication = true;
	onPublished?.();
	fs.unlinkSync(sourcePath);
	return createdPublication;
}
export { moveMigrationArtifact, path };

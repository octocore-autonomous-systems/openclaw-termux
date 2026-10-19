// Synthetic stand-in for fs-safe code inlined into OpenClaw's bundle (test fixture).
import fs from "node:fs";
const HARDLINK_FALLBACK_CODES = new Set(["EPERM", "EXDEV", "ENOTSUP"]);
const NATIVE_COPY_FALLBACK_CODES = new Set(["EINVAL", "ENOTSUP"]);
function publishCopyStage(params, temporaryPath, targetPath, identity) {
	fs.linkSync(temporaryPath, targetPath);
	params.onPublished?.(identity);
}
function normalizeLinkError(code) {
	return (code === "EOPNOTSUPP" || code === "EPERM");
}
async function copyNative(input, native, code, error, parentFd, basename, maxBytes, nativeSignal) {
	if (code === "ENOTSUP" && input.clone !== "always") return null;
	return error;
}
export { HARDLINK_FALLBACK_CODES, NATIVE_COPY_FALLBACK_CODES, copyNative, normalizeLinkError, publishCopyStage };

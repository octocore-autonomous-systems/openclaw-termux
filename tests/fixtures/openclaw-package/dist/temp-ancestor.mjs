// Synthetic stand-in for OpenClaw's temp-root ancestor checks (test fixture).
function admitAncestor(currentIdentity, uid) {
	const writableByOtherUsers = (currentIdentity.mode & 18) !== 0;
	const ownerCanReplaceChild = currentIdentity.uid !== uid && currentIdentity.uid !== 0;
	return !writableByOtherUsers && !ownerCanReplaceChild;
}
export { admitAncestor };

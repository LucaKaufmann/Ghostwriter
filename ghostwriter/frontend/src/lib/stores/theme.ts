import { mode, resetMode, setMode, userPrefersMode } from 'mode-watcher';

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

function getPreference(): ThemePreference {
	return userPrefersMode.current ?? 'system';
}

function getResolved(): ResolvedTheme {
	return mode.current === 'dark' ? 'dark' : 'light';
}

function setPreference(preference: ThemePreference) {
	if (preference === 'system') {
		resetMode();
		return;
	}
	setMode(preference);
}

function cyclePreference() {
	const current = getPreference();
	if (current === 'system') {
		setPreference('light');
		return;
	}
	if (current === 'light') {
		setPreference('dark');
		return;
	}
	setPreference('system');
}

export const theme = {
	get preference(): ThemePreference {
		return getPreference();
	},
	get resolved(): ResolvedTheme {
		return getResolved();
	},
	setPreference,
	cyclePreference
};

export function parseUTC(dateStr: string): Date {
	if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
		return new Date(dateStr + 'Z');
	}
	return new Date(dateStr);
}

export function formatUTCDate(
	dateStr: string,
	options: Intl.DateTimeFormatOptions,
	locale = 'en-US'
): string {
	return parseUTC(dateStr).toLocaleDateString(locale, options);
}

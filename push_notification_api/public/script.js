/*
 * Entry point
 */

const button = document.getElementById("generateToken");
const warning = document.getElementById("jsError");

button.disabled = false;
warning.remove();

button.addEventListener("click", async () => {
	button.disabled = true; // indicate we are busy

	const pipe = asyncPipe(
		ensureNotifications,
		registerServiceWorker,
		subscribeUserToPush,
		saveSubscription,
		showToken,
	);

	try {
		await pipe();
	} catch (err) {
		alert(`Error: ${err?.message ?? err}`);
		button.disabled = false; // no longer busy
	}
});

/*
 * Tasks
 */

// Ensures we have permissions to send notifications.
async function ensureNotifications() {
	if (!("Notification" in window)) {
		throw new Error("This browser does not support notifications");
	} else if (Notification.permission === "granted") {
		/* Yay! Everything is good. */
	} else if (Notification.permission !== "denied") {
		const permission = await Notification.requestPermission();
		if (permission !== "granted") {
			throw new Error("You did not grant notification permissions.");
		}
	}
}

// Installs a service worker. This will be responsible for recieving and
// displaying notifications from the browser's Web Push server.
//
// Note that it takes a bit of time for a new version of the service worker to
// take over. During development, you should probably just clear it manually.
async function registerServiceWorker() {
	if (!('serviceWorker' in navigator)) {
		throw new Error("Service Worker isn't supported on this browser.");
	}
	await navigator.serviceWorker.register("/service-worker.js");
	return navigator.serviceWorker.ready;
}

// Sets up a connection to Web Push if one does not already exist. Returns a PushSubscription.
async function subscribeUserToPush(registration) {
	if (!('PushManager' in window)) {
		throw new Error("Push isn't supported on this browser.");
	}

	const response = await fetch("/api/application-server-key.json");
	if (!response.ok) {
		throw new Error("Failed to fetch key from server");
	}
	const { data: { key } } = await response.json();

	const pushSubscription = await registration.pushManager.getSubscription();
	if (pushSubscription) {
		if (base64ArrayBuffer(pushSubscription.options.applicationServerKey) === key) {
			// The existing subscription is using the same key - no need to do anything furhter.
			console.debug("An existing push subscription with matching key was found.");
			return pushSubscription;
		} else {
			// The existing subscription is using an outdated key. Let's uninstall the old one
			// and continue as if it never existed.
			console.debug("An existing push subscription with a different key was found. Uninstalling...");
			await pushSubscription.unsubscribe();
		}
	}

	// NOTE: The public key should match the key specified in `../keypair/public_key.pem`.
	const subscriptionOptions = {
		userVisibleOnly: true,
		applicationServerKey: key,
	};
	return registration.pushManager.subscribe(subscriptionOptions);
}

// Sends push subscription info (i.e. the endpoint and keys) to the server and
// returns the resulting token.
async function saveSubscription(pushSubscription) {
	const response = await fetch("/api/submit-subscription", {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
		},
		body: JSON.stringify(pushSubscription),
	});
	if (!response.ok) {
		throw new Error("Got invalid resposne upon info submission:" + response.statusText);
	}

	const json = await response.json();
	if (!json.success) {
		throw new Error("API request to store subscription info failed: " + json.info.message);
	}
	return json.data.token;
}

// Display the returned token to the user.
// HACK: please make this less sucky
function showToken(token) {
	const p = document.createElement("P");
	p.append("Your token is ");
	const c = document.createElement("CODE");
	c.textContent = token;
	p.append(c);
	p.append(".");
	button.parentElement.replaceWith(p);

	document.querySelectorAll("em[data-replace-token]").forEach(e => e.replaceWith(token));
}

/*
 * Utils
 */

function asyncPipe(...tasks) {
	tasks = tasks ?? [];

	if (tasks.length === 0) {
		return x => x;
	}

	return async function (request) {
		let index = 0;

		while (index < tasks.length) {
			request = await tasks[index](request);

			console.debug("%s: %o", camelCaseToSentence(tasks[index].name), request);
			index++;
		}

		return request;
	};
}

function camelCaseToSentence(str) {
	return str.replace(/[A-Z]/g, letter => ` ${letter.toLowerCase()}`);
}

// Based on https://gist.github.com/jonleighton/958841
function base64ArrayBuffer(arrayBuffer) {
	let base64    = ''
	const encodings = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'

	const bytes         = new Uint8Array(arrayBuffer)
	const byteLength    = bytes.byteLength
	const byteRemainder = byteLength % 3
	const mainLength    = byteLength - byteRemainder

	let a, b, c, d;
	let chunk;

	// Main loop deals with bytes in chunks of 3
	for (let i = 0; i < mainLength; i = i + 3) {
		// Combine the three bytes into a single integer
		chunk = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]

		// Use bitmasks to extract 6-bit segments from the triplet
		a = (chunk & 16515072) >> 18 // 16515072 = (2^6 - 1) << 18
		b = (chunk & 258048)   >> 12 // 258048   = (2^6 - 1) << 12
		c = (chunk & 4032)     >>  6 // 4032     = (2^6 - 1) << 6
		d = chunk & 63               // 63       = 2^6 - 1

		// Convert the raw binary segments to the appropriate ASCII encoding
		base64 += encodings[a] + encodings[b] + encodings[c] + encodings[d]
	}

	// Deal with the remaining bytes and padding
	if (byteRemainder == 1) {
		chunk = bytes[mainLength]

		a = (chunk & 252) >> 2 // 252 = (2^6 - 1) << 2

		// Set the 4 least significant bits to zero
		b = (chunk & 3)   << 4 // 3   = 2^2 - 1

		base64 += encodings[a] + encodings[b]
	} else if (byteRemainder == 2) {
		chunk = (bytes[mainLength] << 8) | bytes[mainLength + 1]

		a = (chunk & 64512) >> 10 // 64512 = (2^6 - 1) << 10
		b = (chunk & 1008)  >>  4 // 1008  = (2^6 - 1) << 4

		// Set the 2 least significant bits to zero
		c = (chunk & 15)    <<  2 // 15    = 2^4 - 1

		base64 += encodings[a] + encodings[b] + encodings[c]
	}

	return base64;
}

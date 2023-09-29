// Show notifications when they are recieved from the web push server.
self.addEventListener("push", event => {
	const data = event.data.json();
	const notificationPromise = self.registration.showNotification(data.title, {
		body: data.message,
		timestamp: data.timestamp,
		data: data,
		requireInteraction: true,
	});
	event.waitUntil(notificationPromise);
});

// Open linked urls when notifications are clicked.
self.addEventListener("notificationclick", event => {
	event.notification.close();
	if (event.notification.data.url) {
		self.clients.openWindow(event.notification.data.url);
	}
});

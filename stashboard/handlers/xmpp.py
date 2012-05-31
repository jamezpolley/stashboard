# The MIT License
#
# Copyright (c) 2008 William T. Katz
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.


__author__ = 'James Polley'

import os
import sys
import logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'contrib'))

import appengine_config # Make sure this happens

from google.appengine.api import memcache

from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import xmpp_handlers

from models import List, Service, Status, Event, Image, Profile, Subscription
from utils import authorized

class FirstWordHandlerMixin(xmpp_handlers.CommandHandlerMixin):
    """Just like CommandHandlerMixin but assumes first word is command."""

    def message_received(self, message):
        if message.command:
            super(FirstWordHandlerMixin, self).message_received(message)
        else:
            command = message.body.split(' ')[0]
            handler_name = '%s_command' % (command,)
            handler = getattr(self, handler_name, None)
            if handler:
                handler(message)
            else:
                self.unhandled_command(message)

class FirstWordHandler(FirstWordHandlerMixin, xmpp_handlers.BaseHandler):
    """A webapp implementation of FirstWordHandlerMixin."""
    pass

class XmppNotificationHandler(webapp.RequestHandler):
    """Handle notifications via XMPP"""

    def post(self):
        """Notify subscribers that a service changed status."""

        address = self.request.get('address')
        service = Service.get(self.request.get('service'))
        oldstatus = Status.get(self.request.get('oldstatus'))

        logging.info("Service: %s" % service)
        logging.info("Service name: %s" % service.name)

        msg = "%s changed state from %s to %s" % (
                service.name, oldstatus.name,
                service.current_event().status.name)
        xmpp.send_message(address, msg)
        logging.info("Notified: %s\nmessage: %s" % (address, msg))

class XmppHandler(FirstWordHandler):
    """Handler class for all XMPP activity."""

    def service_command(self, message=None):
        """Change status of a service"""
        _, service_name = message.body.split(' ', 1)
        service = Service.all().filter('name = ', service_name).get()

        if service:
            return_msg =["Name: %s" % service.name]
            return_msg.append("Description: %s" % service.description)
            return_msg.append("Recent events:")
            events = service.events.order('-start').run(limit=3)
            for event in events:
                return_msg.append("%s: %s: %s" % (
                        event.start, event.status.name, event.message))
        else:
            return_msg = ["Cannot find service with name: %s" % service_name]

        return_msg = "\n".join(return_msg)
        message.reply(return_msg)

    def services_command(self, message=None):
        """List all services"""
        return_msg = []

        for service in Service.all():
            event = service.current_event()
            if event:
                return_msg.append("%s: %s: %s" % (
                        service.name, event.status.name, event.message))
            else:
                return_msg.append("%s has no events" % service.name)

        return_msg = '\n'.join(return_msg)

        message.reply(return_msg)

    def addservice_command(self, message=None):
        """Create a new service"""

        service_name = message.body.split(' ')[1]
        service = Service(key_name=service_name, name=service_name)
        service.put()

        message.reply("Added service %s" % service_name)

    def sub_command(self, message=None):
        """Subscribe the user to a service"""
        user = message.sender.split('/')[0]

        _, service_name = message.body.split(' ', 1)
        service = Service.all().filter('name = ', service_name).get()

        if service:
            subscription = Subscription.all().filter('address =', user).filter('service = ', service).get()
            if subscription:
                message.reply("user %s is already subscribed to service %s" % (user, service.name))
            else:
                subscription = Subscription(type='xmpp', address=user, service=service)
                subscription.put()
                message.reply("Subscribed %s to service %s" % (user, service.name))
        else:
            message.reply("Sorry, I couldn't find a service called "
                          "%s" % service_name)

    def unsub_command(self, message=None):
        """Unsubscribe the user from a service"""
        user = message.sender.split('/')[0]

        _, service_name = message.body.split(' ', 1)
        service = Service.all().filter('name = ', service_name).get()

        if service:
            subscription = Subscription.all().filter('address =', user).filter('service = ', service).get()
            if subscription:
                subscription.delete()
                message.reply("Unsubscribed %s from service %s" % (user, service.name))
            else:
                message.reply("user %s is not subscribed to service %s" % (user, service.name))
        else:
            message.reply("Sorry, I couldn't find a service called "
                          "%s" % service_name)

#!/bin/bash

LAN=eth0

/etc/rc.d/init.d/iptables stop

iptables -P INPUT   DROP
iptables -P OUTPUT  ACCEPT
iptables -P FORWARD DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# TCP SYN Floood
sysctl -w net.ipv4.tcp_syncookies=1 > /dev/null
sed -i '/net.ipv4.tcp_syncookies/d' /etc/sysctl.conf
echo "net.ipv4.tcp_syncookies=1" >> /etc/sysctl.conf

# Smurf Attack
sysctl -w net.ipv4.icmp_echo_ignore_broadcasts=1 > /dev/null
sed -i '/net.ipv4.icmp_echo_ignore_broadcasts/d' /etc/sysctl.conf
echo "net.ipv4.icmp_echo_ignore_broadcasts=1" >> /etc/sysctl.conf

# Reject ICMP Redirect
sed -i '/net.ipv4.conf.*.accept_redirects/d' /etc/sysctl.conf
for dev in `ls /proc/sys/net/ipv4/conf/`
do
    sysctl -w net.ipv4.conf.$dev.accept_redirects=0 > /dev/null
    echo "net.ipv4.conf.$dev.accept_redirects=0" >> /etc/sysctl.conf
done

# Reject Source Routed packet
sed -i '/net.ipv4.conf.*.accept_source_route/d' /etc/sysctl.conf
for dev in `ls /proc/sys/net/ipv4/conf/`
do
    sysctl -w net.ipv4.conf.$dev.accept_source_route=0 > /dev/null
    echo "net.ipv4.conf.$dev.accept_source_route=0" >> /etc/sysctl.conf
done

# Reject flagment packet
iptables -A INPUT -f -j LOG --log-prefix '[IPTABLES FRAGMENT] : '
iptables -A INPUT -f -j DROP

# Reject ping
iptables -N LOG_PINGDEATH
iptables -A LOG_PINGDEATH -m limit --limit 1/s --limit-burst 4 -j ACCEPT
iptables -A LOG_PINGDEATH -j LOG --log-prefix '[IPTABLES PINGDEATH] : '
iptables -A LOG_PINGDEATH -j DROP
iptables -A INPUT -p icmp --icmp-type echo-request -j LOG_PINGDEATH

# Reject broadcast
iptables -A INPUT -d 255.255.255.255 -j DROP
iptables -A INPUT -d 224.0.0.1 -j DROP

# Reject IDENT
iptables -A INPUT -p tcp --dport 113 -j REJECT --reject-with tcp-reset

#----------------------------------------------------------#
# Services
#----------------------------------------------------------#
# ssh
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# DNS
#iptables -A INPUT -p tcp --dport 53 -j ACCEPT
#iptables -A INPUT -p udp --dport 53 -j ACCEPT

# HTTP
#iptables -A INPUT -p tcp --dport 80 -j ACCEPT

# HTTPS
#iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# FTP
#iptables -A INPUT -p tcp --dport 21 -j ACCEPT

# FTP-DATA
#iptables -A INPUT -p tcp --dport 60000:60030 -j ACCEPT

# SMTP
#iptables -A INPUT -p tcp --dport 25 -j ACCEPT

# SMTPS
#iptables -A INPUT -p tcp --dport 465 -j ACCEPT

# POP3
#iptables -A INPUT -p tcp --dport 110 -j ACCEPT

# POP3S
#iptables -A INPUT -p tcp --dport 995 -j ACCEPT

# IMAP
#iptables -A INPUT -p tcp --dport 143 -j ACCEPT

# IMAPS
#iptables -A INPUT -p tcp --dport 993 -j ACCEPT

# OpenVPN
#iptables -A INPUT -p udp --dport 1194 -j ACCEPT

# Reject others
iptables -A INPUT -m limit --limit 1/s -j LOG --log-prefix '[IPTABLES INPUT] : '
iptables -A INPUT -j DROP
iptables -A FORWARD -m limit --limit 1/s -j LOG --log-prefix '[IPTABLES FORWARD] : '
iptables -A FORWARD -j DROP

/etc/rc.d/init.d/iptables save
/etc/rc.d/init.d/iptables start

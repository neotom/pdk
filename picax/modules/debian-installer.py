# $Progeny$
#
#   Copyright 2004, 2005 Progeny Linux Systems, Inc.
#
#   This file is part of PDK.
#
#   PDK is free software; you can redistribute it and/or modify it
#   under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   PDK is distributed in the hope that it will be useful, but WITHOUT
#   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
#   License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with PDK; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA

"""This module is an add-on to picax that provides support for using the
debian-installer installer on picax-generated media."""

import os
import shutil
import tarfile
import urllib2
import apt_pkg
import picax.config
import picax.media
import picax.log

options = { "inst-base-url": { "config-key": "base-url",
                               "parameter": True },
            "inst-cdrom-path": { "config-key": "cdrom_path",
                                 "parameter": True },
            "inst-preseed-file": { "config-key": "preseed_file",
                                 "parameter": True },
            "inst-debconf-priority": { "config-key": "debconf_priority",
                                 "parameter": True },
            "inst-suite": { "config-key": "suite",
                                 "parameter": True },
            "inst-locale": { "config-key": "locale",
                                 "parameter": True },
            "inst-boot-options": { "config-key": "boot-options",
                                 "parameter": True },
            "inst-keymap": { "config-key": "keymap",
                                 "parameter": True },
            "inst-floppy-path": { "config-key": "floppy_path",
                                  "parameter": True },
            "inst-template-path": { "config-key": "template_path",
                                    "parameter": True,
                                    "parameter-desc": "path",
                                    "doc":
                                    ("Directory tree for first CD files",)
                                    },
            "inst-base-include-list": { "config-key": "base_include_list",
                                        "parameter": True },
            "inst-base-exclude-list": { "config-key": "base_exclude_list",
                                        "parameter": True },
            "inst-udeb-include-list": { "config-key": "udeb_include_list",
                                        "parameter": True },
            "inst-udeb-exclude-list": { "config-key": "udeb_exclude_list",
                                        "parameter": True },
            "inst-timeout": { "config-key": "timeout",
                                 "parameter": True },
            "inst-exclude-task": {"config-key": "exclude-task",
                                  "parameter": True } }

boot_image_map = { "i386": "isolinux/isolinux.bin",
                   "amd64": "isolinux/isolinux.bin",
                   "ia64": "boot/boot.img" }

di_required_packages = [ "eject", "grub" ]

conf = picax.config.get_config()
log = picax.log.get_logger()

def get_options():
    "Return the module's options for the configuration."

    return options

def _get_boot_image_path():
    "Return the path to the boot image."

    if boot_image_map.has_key(conf["arch"]):
        return boot_image_map[conf["arch"]]
    else:
        return None

class DIMediaBuilder(picax.media.MediaBuilder):
    """Build the media in the debian-installer way: put a boot image on
    the first image, and then do the rest the usual way."""

    def create_media(self):
        "Build the media."

        picax.media.create_image(1, _get_boot_image_path())
        index = 2
        while picax.media.can_create_image(index):
            picax.media.create_image(index)
            index = index + 1

def get_media_builder():
    "Return a media builder object to control the building of media."

    return DIMediaBuilder()

def _read_task_info():
    task_info = {}

    (distro, component) = conf["repository_list"][0]
    packages_path = "%s/dists/%s/%s/binary-%s/Packages" \
                    % (conf["base_path"], distro, component, conf["arch"])
    packages_file = open(packages_path)
    packages = apt_pkg.ParseTagFile(packages_file)

    while packages.Step() == 1:
        if packages.Section.has_key("Task"):
            pkg = packages.Section["Package"]
            task = packages.Section["Task"]
            if not task_info.has_key(task):
                task_info[task] = []
            task_info[task].append(pkg)

    packages_file.close()
    return task_info

def get_package_requests():
    "Retrieve the packages needed by debian-installer on the early media."

    inst_conf = conf["installer_options"]
    task_info = _read_task_info()

    pkgs = []
    pkgs.extend(di_required_packages)
    for task in task_info.keys():
        if not inst_conf.has_key("exclude-task") or \
           task not in inst_conf["exclude-task"].split(","):
            pkgs.extend(task_info[task])

    return pkgs

def _dos_tr(unixstr):
    return unixstr.replace("\n", "\r\n")

def _copy_template(cd_path):
    inst_conf = conf["installer_options"]
    if inst_conf.has_key("template_path") and \
       os.path.isdir(inst_conf["template_path"]):
        for template_fn in os.listdir(inst_conf["template_path"]):
            if template_fn[0] == ".":
                continue
            template_path = "%s/%s" % (inst_conf["template_path"],
                                       template_fn)
            if os.path.isdir(template_path):
                shutil.copytree(template_path,
                                "%s/%s" % (cd_path, template_fn))
            else:
                shutil.copy2(template_path, cd_path)

def _download_di_base(base_uri, dest_path, file_list):
    if not os.path.isdir(dest_path):
        os.makedirs(dest_path)

    for image in file_list:
        input_file = urllib2.urlopen("%s/%s" % (base_uri, image))
        output_file = open(dest_path + "/" + image, "w")
        output_file.write(input_file.read())
        input_file.close()
        output_file.close()

def _download_preseed(preseed_uri, cd_path):
    if not os.path.isdir(cd_path):
        os.makedirs(cd_path)

    input_file = urllib2.urlopen(preseed_uri)
    output_file = open(cd_path + "/.disk/preseed", "w")
    output_file.write(input_file.read())
    input_file.close()
    output_file.close()

def _install_common(cd_path):
    log.info("Installing debian-installer common files")

    inst_conf = conf["installer_options"]
    component = conf["repository_list"][0][1]

    for isodir in (".disk",):
        if not os.path.isdir(cd_path + "/" + isodir):
            os.mkdir(cd_path + "/" + isodir)

    compfile = open(cd_path + "/.disk/base_components", "w")
    compfile.write(component + "\n")
    compfile.close()

    compfile = open(cd_path + "/.disk/base_installable", "w")
    compfile.close()

    for (key, fn) in (("base_include_list", "base_include"),
                      ("base_exclude_list", "base_exclude"),
                      ("udeb_include_list", "udeb_include"),
                      ("udeb_include_list", "udeb_include")):
        if inst_conf.has_key(key):
		diskfile = open("%s/.disk/%s" % (cd_path, fn), "w")
		diskfile.write('\n'.join(inst_conf[key].split(' ')) + "\n")
		diskfile.close()

    if inst_conf.has_key("preseed_file"):
        _download_preseed(inst_conf["preseed_file"], cd_path)    

def _install_i386(cd_path):
    boot_image_list = ["initrd.gz", "vmlinuz",
                       "debian-cd_info.tar.gz"]

    inst_conf = conf["installer_options"]
    base_url = inst_conf["base-url"]

    log.info("Installing debian-installer for %s" % (conf["arch"],))

    for isodir in ("isolinux", "install"):
        if not os.path.isdir(cd_path + "/" + isodir):
            os.mkdir(cd_path + "/" + isodir)

    dl_path = conf["temp_dir"] + "/di-download"
    os.mkdir(dl_path)

    image_path = dl_path + "/" + inst_conf["cdrom_path"]

    try:
        _download_di_base("%s/%s" % (base_url, inst_conf["cdrom_path"]),
                          image_path, boot_image_list)

        isolinux_bin = "/usr/lib/pdk/isolinux.bin"
        if not os.path.exists(isolinux_bin):
            raise RuntimeError, "you must have isolinux installed"
        shutil.copyfile(isolinux_bin,
                        cd_path + "/isolinux/isolinux.bin")

        shutil.copyfile(image_path + "/vmlinuz",
                        cd_path + "/install/vmlinuz")
        shutil.copyfile(image_path + "/initrd.gz",
                        cd_path + "/install/initrd.gz")

        isohelp = tarfile.open(image_path + "/debian-cd_info.tar.gz")
        for tarmember in isohelp.getmembers():
            if not os.path.exists("%s/isolinux/%s" % (cd_path,
                                                      tarmember.name)):
                isohelp.extract(tarmember, cd_path + "/isolinux")
        isohelp.close()

        extra_append = ''
        timeout = '0'

        if inst_conf.has_key("preseed_file"):
            extra_append += 'preseed/file=/cdrom/.disk/preseed '
        if inst_conf.has_key("debconf_priority"):
            extra_append += 'debconf/priority=%s ' % inst_conf["debconf_priority"]
        if inst_conf.has_key("suite"):
            extra_append += 'mirror/suite=%s ' % inst_conf["suite"]
            extra_append += 'cdrom/codename=%s ' % inst_conf["suite"]
        if inst_conf.has_key("locale"):
            extra_append += 'debian-installer/locale=%s ' % inst_conf["locale"]
        if inst_conf.has_key("boot-options"):
            extra_append += inst_conf["boot-options"]
        if inst_conf.has_key("keymap"):
            extra_append += 'console-keymaps-at/keymap=%s ' % inst_conf["keymap"]
        if inst_conf.has_key("timeout"):
            timeout = inst_conf["timeout"]

        isocfg = open(cd_path + "/isolinux/isolinux.cfg", "w")
        isocfg.write("""
DISPLAY boot.txt

F1 f1.txt
F2 f2.txt
F3 f3.txt
F4 f4.txt
F5 f5.txt
F6 f6.txt
F7 f7.txt
F8 f8.txt
F9 f9.txt
F0 f10.txt

DEFAULT install

LABEL install
	kernel /install/vmlinuz
	append vga=normal initrd=/install/initrd.gz ramdisk_size=16000 root=/dev/ram rw %s  --
LABEL linux
	kernel /install/vmlinuz
	append vga=normal initrd=/install/initrd.gz ramdisk_size=16000 root=/dev/ram rw %s  --

LABEL expert
	kernel /install/vmlinuz
	append DEBCONF_PRIORITY=low vga=normal initrd=/install/initrd.gz ramdisk_size=16000 root=/dev/ram rw %s  --

LABEL rescue
	kernel /install/vmlinuz
	append vga=normal initrd=/install/initrd.gz ramdisk_size=16000 root=/dev/ram rw  rescue/enable=true --

PROMPT 1
TIMEOUT %s
""" % (extra_append, extra_append, extra_append, timeout))
        isocfg.close()

    finally:
        shutil.rmtree(dl_path)

_install_amd64 = _install_i386

def _install_ia64(cd_path):
    print "Installing debian-installer for %s..." % (conf["arch"],)

    inst_conf = conf["installer_options"]

    for isodir in ("boot",):
        if not os.path.isdir(cd_path + "/" + isodir):
            os.mkdir(cd_path + "/" + isodir)

    _download_di_base("%s/%s" % (inst_conf["base-url"],
                                 inst_conf["cdrom_path"]),
                      cd_path + "/boot", ("boot.img",))

def install(cd_path):
    "Write the installer to the path specified."

    arch_specific_install = globals()["_install_" + conf["arch"]]

    _copy_template(cd_path)
    _install_common(cd_path)
    arch_specific_install(cd_path)

def post_install(cd_path):
    """Do anything needed by d-i after the packages are packed to the
    media."""

    inst_conf = conf["installer_options"]

    dist_path = cd_path + "/dists/"
    distro = conf["repository_list"][0][0]

    links = ["frozen", "testing", "stable", "unstable"]
    if inst_conf.has_key("suite"):
            links.append(inst_conf["suite"])

    for link in tuple(links):
        if not os.path.exists(dist_path + link):
            os.symlink(distro, dist_path + link)

# vim:set ai et sw=4 ts=4 tw=75:

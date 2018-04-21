function setCookie(cname, cvalue, expirationDays) {
    var d = new Date();
    d.setTime(d.getTime() + (expirationDays*24*60*60*1000));
    var expires = "expires="+ d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}

function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function checkCookie() {
    var forum_archive_uid = getCookie("forum_archive_uid");
    if (forum_archive_uid == "") {
        forum_archive_uid = uuidv4();
        if (forum_archive_uid != "" && forum_archive_uid != null) {
            setCookie("forum_archive_uid", forum_archive_uid, 365);
        }
    }
    return forum_archive_uid;
}

function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
   });
}


function cloudClick(area) {
  var linkTarget = area.href
  area.setAttribute("href", linkTarget + "&uid=" + uid);
}
                                 

var uid   = checkCookie("uid");

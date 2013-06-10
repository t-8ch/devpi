import pytest

class TestUserThings:
    def test_root_cannot_modify_unknown_user(self, mapp):
        mapp.login_root()
        mapp.modify_user("/user", password="123", email="whatever",
                         code=404)

    def test_root_is_refused_with_wrong_password(self, mapp):
        mapp.login("root", "123123", code=401)

    def test_create_and_delete_user(self, mapp):
        password = "somepassword123123"
        assert "hello" not in mapp.getuserlist()
        mapp.create_user("hello", password)
        mapp.create_user("hello", password, code=409)
        assert "hello" in mapp.getuserlist()
        mapp.login("hello", "qweqwe", code=401)
        mapp.login("hello", password)
        mapp.delete_user("hello")
        mapp.login("hello", password, code=401)
        assert "hello" not in mapp.getuserlist()

    def test_delete_not_existent_user(self, mapp):
        mapp.login("root", "")
        mapp.delete_user("qlwkje", code=404)

    def test_password_setting_admin(self, mapp):
        mapp.login("root", "")
        mapp.change_password("root", "p1oi2p3i")
        mapp.login("root", "p1oi2p3i")


class TestIndexThings:

    def test_create_index(self, mapp):
        mapp.create_and_login_user()
        indexname = mapp.auth[0] + "/dev"
        assert indexname not in mapp.getindexlist()
        mapp.create_index("dev")
        assert indexname in mapp.getindexlist()

    def test_create_index__not_exists(self, mapp):
        mapp.create_index("not_exist/dev", code=404)

    def test_create_index_default_allowed(self, mapp):
        mapp.create_index("root/test1")
        mapp.login("root", "")
        mapp.change_password("root", "asd")
        mapp.create_and_login_user("newuser1")
        mapp.create_index("root/test2", 401)

    @pytest.mark.parametrize(["input", "expected"], [
        ({},
          dict(type="stage", volatile=True, bases=["root/dev", "root/pypi"])),
        ({"volatile": "False"},
          dict(type="stage", volatile=False, bases=["root/dev", "root/pypi"])),
        ({"volatile": "False", "bases": "root/pypi"},
          dict(type="stage", volatile=False, bases=["root/pypi"])),
        ({"volatile": "False", "bases": ["root/pypi"]},
          dict(type="stage", volatile=False, bases=["root/pypi"])),
    ])
    def test_kvdict(self, input, expected):
        from devpi_server.views import getkvdict_index
        result = getkvdict_index(input)
        assert result == expected

    def test_config_get_user_empty(self, mapp):
        mapp.getjson("/user", code=404)

    def test_create_user_and_config_gets(self, mapp):
        assert mapp.getjson("/")["type"] == "list:userconfig"
        mapp.create_and_login_user("cuser1")
        data = mapp.getjson("/cuser1")
        assert data["type"] == "userconfig"
        data = mapp.getjson("/cuser1/")
        assert data["type"] == "list:indexconfig"

    def test_create_index_and_config_gets(self, mapp):
        mapp.create_and_login_user("cuser2")
        mapp.create_index("dev")
        assert mapp.getjson("/cuser2/dev")["type"] == "indexconfig"
        assert mapp.getjson("/cuser2/dev/")["type"] == "list:projectconfig"

    def test_create_project_config_gets(self, mapp):
        mapp.create_and_login_user("cuser3")
        mapp.create_index("dev")
        mapp.create_project("dev", "hello")
        assert mapp.getjson("/cuser3/dev/")["type"] == "list:projectconfig"
        assert mapp.getjson("/cuser3/dev/hello")["type"] == "projectconfig"
        mapp.create_project("dev", "hello", code=409)



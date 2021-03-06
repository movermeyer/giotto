import unittest
from giotto.exceptions import NoViewMethod
from giotto.views import GiottoView, BasicView, renders
from giotto.control import Redirection

class Blog(object):
    def __init__(self, id=None, title=None, body=None):
        self.id = id
        self.title = title
        self.body = body

    def __repr__(self):
        return "%s %s %s" % (self.id, self.title, self.body)

class RendererTests(unittest.TestCase):
    giotto_view = GiottoView()
    basic_view = BasicView()

    def test_mising_renderer(self):
        """
        Exception is raises when you try to render mimetype that is not
        supported by the view class
        """
        assert self.giotto_view.can_render('text/html') == False
        self.assertRaises(NoViewMethod, lambda: self.giotto_view.render({}, 'text/html'))

    def test_render_defined_mimetype(self):
        assert self.basic_view.can_render('text/html') == True
        result = self.basic_view.render({}, 'text/html')
        assert 'body' in result

    def test_kwarg_renderer(self):
        """
        Renderers passed into the constructor override renderers defined on the
        class.
        """
        view = BasicView(html=lambda m: "inherited")
        result = view.render({}, 'text/html')
        self.assertEquals(result['body'], "inherited")

    def test_redirection_lambda(self):
        view = BasicView(html=lambda m: Redirection(m))
        result = view.render('res', 'text/html')
        self.assertEquals(type(result['body']), Redirection)
        self.assertEquals(result['body'].path, 'res')

    def test_redirection(self):
        view = BasicView(html=Redirection('/'))
        result = view.render({}, 'text/html')
        self.assertEquals(type(result['body']), Redirection)
        self.assertEquals(result['body'].path, '/')

    def test_subclass_renderer(self):
        """
        A Renderer that is defined on a class takes precidence over the renderer
        defined in a base class. Regardless of the name of the render method function.
        """
        class InheritedBasicView1(BasicView):
            @renders('text/html')
            def a(self, result, errors):
                # show up earlier than 'generic_html' in dir()
                return 'inherited'

        class InheritedBasicView2(BasicView):
            @renders('text/html')
            def zzzzzzz(self, result, errors):
                # show up later than 'generic_html' in dir()
                return 'inherited'

        for view in [InheritedBasicView2(), InheritedBasicView1()]:
            result = view.render({}, 'text/html')
            self.assertEquals(result['body'], "inherited")

class TestGenericView(unittest.TestCase):
    def test_list_html(self):
        result = BasicView().render(['one', 'two'], 'text/html')['body']
        assert '<html>' in result
        assert 'one' in result

    def test_list_txt(self):
        result = BasicView().render(['one', 'two'], 'text/plain')['body']
        assert 'two' in result
        assert 'one' in result

    def test_dict_html(self):
        result = BasicView().render({'one': 'two'}, 'text/html')['body']
        assert '<html>' in result
        assert 'one' in result

    def test_dict_txt(self):
        result = BasicView().render({'one': 'two'}, 'text/plain')['body']
        assert 'one - two' in result

    def test_objects_txt(self):
        blogs = [Blog(title="title", body="This blog body"), Blog(title="title2", body="blog body two")]
        result = BasicView().render(blogs, 'text/plain')['body']
        assert 'blog body two' in result
        assert 'This blog body' in result

    def test_objects(self):
        blogs = [Blog(title="title", body="This blog body"), Blog(title="title2", body="blog body two")]
        result = BasicView().render(blogs, 'text/html')['body']
        assert 'blog body two' in result
        assert 'This blog body' in result
        assert '<!DOCTYPE html>' in result

    def test_string(self):
        result = BasicView().render("just a simple string", 'text/html')['body']
        assert "just a simple string" in result

    def test_nonetype(self):
        result = BasicView().render(None, 'text/html')['body']
        assert "None" in result


if __name__ == '__main__':
    unittest.main()